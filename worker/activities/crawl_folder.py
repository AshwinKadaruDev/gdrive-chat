"""Activity: recursively crawl a Google Drive folder and list all files."""

from __future__ import annotations

import logging

import httpx
from temporalio import activity

logger = logging.getLogger(__name__)

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"


@activity.defn
async def crawl_folder(folder_id: str, access_token: str) -> list[dict]:
    """Recursively list all files in a Google Drive folder.

    Returns a list of file metadata dicts with keys:
        id, name, mimeType, size, webViewLink, hierarchy
    """
    all_files: list[dict] = []
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        await _crawl_recursive(client, headers, folder_id, "", all_files)

    activity.logger.info("Crawled folder %s: found %d files", folder_id, len(all_files))
    return all_files


async def _crawl_recursive(
    client: httpx.AsyncClient,
    headers: dict,
    folder_id: str,
    parent_path: str,
    results: list[dict],
) -> None:
    """Recursively traverse a Google Drive folder."""
    page_token: str | None = None

    while True:
        params: dict = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType, size, webViewLink)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token

        response = await client.get(DRIVE_FILES_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        for item in data.get("files", []):
            current_path = f"{parent_path}/{item['name']}" if parent_path else item["name"]

            if item["mimeType"] == "application/vnd.google-apps.folder":
                # Recurse into sub-folders
                await _crawl_recursive(client, headers, item["id"], current_path, results)
            else:
                results.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "mimeType": item["mimeType"],
                        "size": item.get("size"),
                        "webViewLink": item.get("webViewLink", ""),
                        "hierarchy": current_path,
                    }
                )

        page_token = data.get("nextPageToken")
        if not page_token:
            break
