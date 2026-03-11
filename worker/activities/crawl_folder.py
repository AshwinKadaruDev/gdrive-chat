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
    activity.logger.info("[CRAWL] Starting crawl for folder_id=%s", folder_id)
    activity.logger.info("[CRAWL] Access token length=%d", len(access_token))

    all_files: list[dict] = []
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        await _crawl_recursive(client, headers, folder_id, "", all_files)

    activity.logger.info("[CRAWL] Finished crawling folder %s: found %d files total", folder_id, len(all_files))
    for f in all_files:
        activity.logger.info("[CRAWL]   file: %s (type=%s, size=%s)", f["hierarchy"], f["mimeType"], f.get("size"))
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
    logger.info("[CRAWL] Listing contents of folder_id=%s (path=%s)", folder_id, parent_path or "<root>")

    while True:
        params: dict = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType, size, webViewLink)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token

        logger.info("[CRAWL] Drive API request: folder_id=%s, query=%s", folder_id, params["q"])
        response = await client.get(DRIVE_FILES_URL, headers=headers, params=params)
        logger.info("[CRAWL] Drive API response: status=%d", response.status_code)

        if response.status_code != 200:
            logger.error("[CRAWL] Drive API error: status=%d body=%s", response.status_code, response.text[:500])
            response.raise_for_status()

        data = response.json()
        items = data.get("files", [])
        logger.info("[CRAWL] Got %d items from folder_id=%s", len(items), folder_id)

        for item in items:
            current_path = f"{parent_path}/{item['name']}" if parent_path else item["name"]

            if item["mimeType"] == "application/vnd.google-apps.folder":
                logger.info("[CRAWL] Found subfolder: %s (id=%s) — recursing", current_path, item["id"])
                await _crawl_recursive(client, headers, item["id"], current_path, results)
            else:
                logger.info("[CRAWL] Found file: %s (type=%s, size=%s)", current_path, item["mimeType"], item.get("size"))
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
