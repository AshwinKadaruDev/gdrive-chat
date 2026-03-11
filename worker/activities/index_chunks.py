"""Activity: index processed chunks into Azure AI Search."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from temporalio import activity

logger = logging.getLogger(__name__)

UPLOAD_BATCH_SIZE = 100  # Azure Search upload limit per request is 1000, keep conservative


@activity.defn
async def index_chunks(chunks: list[dict], project_id: str) -> dict:
    """Upsert chunks into Azure AI Search.

    Adds project_id and created_at to each chunk, then uploads them.
    Returns {"indexed": int}.
    """
    if not chunks:
        return {"indexed": 0}

    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY", "")
    index_name = os.environ.get("AZURE_SEARCH_INDEX_NAME", "talk-to-folder-chunks")

    if not endpoint or not api_key:
        raise RuntimeError(
            "AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY environment variables are required"
        )

    credential = AzureKeyCredential(api_key)
    client = SearchClient(
        endpoint=endpoint,
        index_name=index_name,
        credential=credential,
    )

    now = datetime.now(timezone.utc).isoformat()

    # Prepare documents for upload
    documents = []
    for chunk in chunks:
        doc = {
            "id": chunk.get("chunk_id", ""),
            "chunk_id": chunk.get("chunk_id", ""),
            "text": chunk.get("text", ""),
            "file_id": chunk.get("file_id", ""),
            "file_name": chunk.get("file_name", ""),
            "file_type": chunk.get("file_type", ""),
            "hierarchy": chunk.get("hierarchy", ""),
            "source_url": chunk.get("source_url", ""),
            "section_heading": chunk.get("section_heading", ""),
            "page_number": chunk.get("page_number"),
            "sheet_name": chunk.get("sheet_name"),
            "project_id": project_id,
            "created_at": now,
            "questions": chunk.get("questions", []),
        }

        # Add vectors if present
        content_vector = chunk.get("content_vector")
        if content_vector:
            doc["content_vector"] = content_vector

        questions_vector = chunk.get("questions_vector")
        if questions_vector:
            doc["questions_vector"] = questions_vector

        documents.append(doc)

    # Upload in batches
    total_indexed = 0
    for i in range(0, len(documents), UPLOAD_BATCH_SIZE):
        batch = documents[i : i + UPLOAD_BATCH_SIZE]
        try:
            result = client.upload_documents(documents=batch)
            succeeded = sum(1 for r in result if r.succeeded)
            failed = len(batch) - succeeded
            if failed > 0:
                activity.logger.warning(
                    "Batch %d: %d succeeded, %d failed",
                    i // UPLOAD_BATCH_SIZE,
                    succeeded,
                    failed,
                )
            total_indexed += succeeded
        except Exception as e:
            activity.logger.error("Failed to index batch starting at %d: %s", i, e)
            raise

    activity.logger.info("Indexed %d chunks for project %s", total_indexed, project_id)
    return {"indexed": total_indexed}
