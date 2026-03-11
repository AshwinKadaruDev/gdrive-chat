import httpx


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

    async def list_folder(
        self, folder_id: str, access_token: str
    ) -> list[dict]:
        """
        Recursively list all files in a Google Drive folder.

        Returns a flat list of file metadata dicts with keys:
        id, name, mimeType, size, modifiedTime, parents, webViewLink.
        """
        all_files: list[dict] = []
        await self._list_folder_recursive(folder_id, access_token, all_files)
        return all_files

    async def _list_folder_recursive(
        self,
        folder_id: str,
        access_token: str,
        accumulator: list[dict],
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

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/files",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            files = data.get("files", [])
            for file in files:
                accumulator.append(file)
                # If the file is a folder, recurse into it
                if file.get("mimeType") == "application/vnd.google-apps.folder":
                    await self._list_folder_recursive(
                        file["id"], access_token, accumulator
                    )

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    async def download_file(self, file_id: str, access_token: str) -> bytes:
        """Download the content of a file from Google Drive."""
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/files/{file_id}"
        params = {"alt": "media"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.content

    async def export_google_doc(
        self,
        file_id: str,
        access_token: str,
        mime_type: str = "text/plain",
    ) -> str:
        """Export a Google Docs/Sheets/Slides file to the specified MIME type."""
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/files/{file_id}/export"
        params = {"mimeType": mime_type}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.text

    async def search_files(
        self,
        folder_id: str,
        query: str,
        access_token: str,
        file_types: list[str] | None = None,
        max_results: int = 20,
    ) -> list[dict]:
        """
        Search for files in a Drive folder using fullText contains.

        Returns a list of file metadata dicts matching the query.
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        # Build the query: scoped to folder, full-text search, not trashed
        # Escape single quotes in query
        escaped_query = query.replace("\\", "\\\\").replace("'", "\\'")
        q_parts = [
            f"'{folder_id}' in parents",
            f"fullText contains '{escaped_query}'",
            "trashed = false",
        ]

        # Optional MIME type filtering
        if file_types:
            mime_clauses = [
                f"mimeType contains '{ft}'" for ft in file_types
            ]
            q_parts.append(f"({' or '.join(mime_clauses)})")

        q = " and ".join(q_parts)

        all_files: list[dict] = []
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
                response.raise_for_status()
                data = response.json()

            all_files.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

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
