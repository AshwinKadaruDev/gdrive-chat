import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class DriveValidationError(Exception):
    """Raised when a Google Drive folder fails validation."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class GoogleDriveService:
    """Service for interacting with the Google Drive API v3."""

    BASE_URL = "https://www.googleapis.com/drive/v3"

    FIELDS = "files(id,name,mimeType,size,modifiedTime,parents,webViewLink)"

    def __init__(self) -> None:
        self._folder_tree_cache: dict[str, list[dict]] = {}

    async def list_folder(
        self, folder_id: str, access_token: str
    ) -> list[dict]:
        """
        Recursively list all files in a Google Drive folder.

        Returns a flat list of file metadata dicts with keys:
        id, name, mimeType, size, modifiedTime, parents, webViewLink.
        """
        logger.info("[DRIVE] list_folder called for folder_id=%s", folder_id)
        all_files: list[dict] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            await self._list_folder_recursive(folder_id, access_token, all_files, client)
        file_count = sum(
            1 for f in all_files
            if f.get("mimeType") != "application/vnd.google-apps.folder"
        )
        logger.info(
            "[DRIVE] list_folder complete: %d items total, %d non-folder files",
            len(all_files), file_count,
        )
        return all_files

    async def count_files(self, folder_id: str, access_token: str) -> int:
        """Count non-folder files recursively in a Google Drive folder."""
        all_items = await self.list_folder(folder_id, access_token)
        count = sum(
            1 for f in all_items
            if f.get("mimeType") != "application/vnd.google-apps.folder"
        )
        logger.info("[DRIVE] count_files: folder=%s → %d files", folder_id, count)
        return count

    async def _list_folder_recursive(
        self,
        folder_id: str,
        access_token: str,
        accumulator: list[dict],
        client: httpx.AsyncClient,
    ) -> None:
        """Recursively traverse a folder and its sub-folders."""
        headers = {"Authorization": f"Bearer {access_token}"}
        page_token: str | None = None

        while True:
            params: dict[str, str] = {
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": f"nextPageToken,{self.FIELDS}",
                "pageSize": "1000",
            }
            if page_token:
                params["pageToken"] = page_token

            response = await client.get(
                f"{self.BASE_URL}/files",
                headers=headers,
                params=params,
            )
            logger.info(
                "[DRIVE] API list folder_id=%s → status=%d, items=%s",
                folder_id, response.status_code,
                len(response.json().get("files", [])) if response.status_code == 200 else "N/A",
            )
            if response.status_code != 200:
                logger.error("[DRIVE] API error: %s", response.text[:500])
            response.raise_for_status()
            data = response.json()

            files = data.get("files", [])
            subfolders = []
            for file in files:
                accumulator.append(file)
                if file.get("mimeType") == "application/vnd.google-apps.folder":
                    logger.info("[DRIVE] Recursing into subfolder: %s (id=%s)", file["name"], file["id"])
                    subfolders.append(file["id"])

            if subfolders:
                await asyncio.gather(*(
                    self._list_folder_recursive(sf_id, access_token, accumulator, client)
                    for sf_id in subfolders
                ))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    async def download_file(self, file_id: str, access_token: str) -> bytes:
        """Download the content of a file from Google Drive."""
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/files/{file_id}"
        params = {"alt": "media"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.content

    async def export_google_doc(
        self,
        file_id: str,
        access_token: str,
        mime_type: str = "text/plain",
        as_bytes: bool = False,
    ) -> str | bytes:
        """Export a Google Docs/Sheets/Slides file to the specified MIME type.

        When *as_bytes* is True the raw response bytes are returned (needed
        for binary formats like xlsx).  Otherwise the decoded text is returned.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/files/{file_id}/export"
        params = {"mimeType": mime_type}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.content if as_bytes else response.text

    async def search_files(
        self,
        folder_id: str,
        query: str,
        access_token: str,
        file_types: list[str] | None = None,
        max_results: int = 20,
    ) -> list[dict]:
        """
        Search for files in a Drive folder **recursively** using fullText contains.

        Collects all subfolder IDs via list_folder, then builds an OR clause
        across all parent IDs so files in nested subfolders are found.
        """
        logger.info("[DRIVE] search_files: folder=%s query=%r file_types=%s", folder_id, query, file_types)
        headers = {"Authorization": f"Bearer {access_token}"}

        # Collect all folder IDs (root + subfolders) for recursive search
        # Use per-instance cache to avoid re-listing within the same request
        if folder_id in self._folder_tree_cache:
            all_items = self._folder_tree_cache[folder_id]
        else:
            all_items = await self.list_folder(folder_id, access_token)
            self._folder_tree_cache[folder_id] = all_items
        folder_ids = [folder_id] + [
            f["id"] for f in all_items
            if f.get("mimeType") == "application/vnd.google-apps.folder"
        ]
        logger.info("[DRIVE] search_files: searching across %d folders", len(folder_ids))

        escaped_query = query.replace("\\", "\\\\").replace("'", "\\'")

        # Google Drive API has query length limits; batch into groups of 30
        all_files: list[dict] = []
        seen_ids: set[str] = set()
        batch_size = 30

        for batch_start in range(0, len(folder_ids), batch_size):
            if len(all_files) >= max_results:
                break

            batch_folders = folder_ids[batch_start : batch_start + batch_size]
            parents_clause = " or ".join(
                f"'{fid}' in parents" for fid in batch_folders
            )

            q_parts = [
                f"({parents_clause})",
                f"fullText contains '{escaped_query}'",
                "trashed = false",
            ]

            if file_types:
                mime_clauses = [
                    f"mimeType contains '{ft}'" for ft in file_types
                ]
                q_parts.append(f"({' or '.join(mime_clauses)})")

            q = " and ".join(q_parts)

            page_token: str | None = None
            while len(all_files) < max_results:
                params: dict[str, str | int] = {
                    "q": q,
                    "fields": f"nextPageToken,{self.FIELDS}",
                    "pageSize": str(min(max_results - len(all_files), 100)),
                }
                if page_token:
                    params["pageToken"] = page_token

                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.BASE_URL}/files",
                        headers=headers,
                        params=params,
                    )
                    if response.status_code != 200:
                        logger.error("[DRIVE] search_files API error: status=%d body=%s", response.status_code, response.text[:500])
                    response.raise_for_status()
                    data = response.json()

                batch = data.get("files", [])
                logger.info("[DRIVE] search_files: got %d results in this page", len(batch))
                for f in batch:
                    fid = f.get("id", "")
                    if fid not in seen_ids:
                        seen_ids.add(fid)
                        all_files.append(f)

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        logger.info("[DRIVE] search_files: returning %d results total", min(len(all_files), max_results))
        return all_files[:max_results]

    async def validate_folder(self, folder_id: str, access_token: str) -> dict:
        """
        Validate that a folder_id points to an accessible Google Drive folder.

        Returns metadata dict ``{id, name, mimeType, webViewLink}`` on success.
        Raises ``DriveValidationError`` on any failure.
        """
        try:
            metadata = await self.get_file_metadata(folder_id, access_token)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise DriveValidationError(
                    "not_found",
                    "We couldn't find that folder. Double-check the URL and "
                    "make sure the folder hasn't been deleted.",
                )
            if exc.response.status_code == 403:
                raise DriveValidationError(
                    "no_access",
                    "You don't have access to this folder. Ask the owner to "
                    "share it with your Google account.",
                )
            raise DriveValidationError(
                "drive_error",
                "Something went wrong connecting to Google Drive. Please try again.",
            )

        if metadata.get("mimeType") != "application/vnd.google-apps.folder":
            raise DriveValidationError(
                "not_a_folder",
                "That URL points to a file, not a folder. "
                "Please paste a link to a Google Drive folder.",
            )

        return {
            "id": metadata["id"],
            "name": metadata["name"],
            "mimeType": metadata["mimeType"],
            "webViewLink": metadata.get("webViewLink"),
        }

    async def get_file_metadata(self, file_id: str, access_token: str) -> dict:
        """Get metadata for a single file."""
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/files/{file_id}"
        params = {
            "fields": "id,name,mimeType,size,modifiedTime,parents,webViewLink,description",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
