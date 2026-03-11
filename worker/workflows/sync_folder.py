"""SyncFolderWorkflow -- orchestrates the full folder-sync pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from worker.activities.crawl_folder import crawl_folder
    from worker.activities.extract_content import extract_content
    from worker.activities.chunk_content import chunk_content
    from worker.activities.generate_embeddings import generate_embeddings
    from worker.activities.generate_questions import generate_questions
    from worker.activities.index_chunks import index_chunks

logger = logging.getLogger(__name__)


@dataclass
class SyncInput:
    """Input for the SyncFolderWorkflow."""

    project_id: str
    folder_id: str
    user_access_token: str
    user_refresh_token: str


@workflow.defn
class SyncFolderWorkflow:
    """Crawl a Google Drive folder, extract content, chunk, embed, and index."""

    @workflow.run
    async def run(self, input: SyncInput) -> dict:
        workflow.logger.info(
            "SyncFolderWorkflow started for project=%s folder=%s",
            input.project_id,
            input.folder_id,
        )

        # Step 1: Crawl folder to discover all files
        files = await workflow.execute_activity(
            crawl_folder,
            args=[input.folder_id, input.user_access_token],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=workflow.RetryPolicy(maximum_attempts=3),
        )

        workflow.logger.info("Discovered %d files in folder %s", len(files), input.folder_id)

        if not files:
            return {
                "project_id": input.project_id,
                "folder_id": input.folder_id,
                "total_files": 0,
                "processed_files": 0,
                "failed_files": 0,
                "indexed_chunks": 0,
            }

        # Step 2: Process each file through the extraction pipeline
        all_chunks: list[dict] = []
        failed_count = 0

        for file_info in files:
            try:
                # 2a. Extract content from the file
                extracted = await workflow.execute_activity(
                    extract_content,
                    args=[file_info, input.user_access_token],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=2),
                )

                # Skip files with no extractable text
                if not extracted or not extracted.get("text", "").strip():
                    workflow.logger.info(
                        "Skipping file %s (no text extracted)", file_info.get("name", "unknown")
                    )
                    continue

                # 2b. Chunk the extracted content
                chunks = await workflow.execute_activity(
                    chunk_content,
                    args=[extracted, file_info],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=2),
                )

                if not chunks:
                    continue

                # 2c. Generate embeddings for chunks
                chunks_with_embeddings = await workflow.execute_activity(
                    generate_embeddings,
                    args=[chunks],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=3),
                )

                # 2d. Generate hypothetical questions and their embeddings
                chunks_with_questions = await workflow.execute_activity(
                    generate_questions,
                    args=[chunks_with_embeddings],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=2),
                )

                all_chunks.extend(chunks_with_questions)

            except Exception as e:
                failed_count += 1
                workflow.logger.error(
                    "Failed to process file %s: %s",
                    file_info.get("name", "unknown"),
                    str(e),
                )
                # Continue with remaining files
                continue

        # Step 3: Batch index all processed chunks
        indexed_count = 0
        if all_chunks:
            # Index in batches of 500 to avoid payload size limits
            batch_size = 500
            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i : i + batch_size]
                result = await workflow.execute_activity(
                    index_chunks,
                    args=[batch, input.project_id],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=3),
                )
                indexed_count += result.get("indexed", 0)

        summary = {
            "project_id": input.project_id,
            "folder_id": input.folder_id,
            "total_files": len(files),
            "processed_files": len(files) - failed_count,
            "failed_files": failed_count,
            "indexed_chunks": indexed_count,
        }

        workflow.logger.info("SyncFolderWorkflow completed: %s", summary)
        return summary
