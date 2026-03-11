"""SyncFolderWorkflow -- orchestrates the full folder-sync pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from worker.activities.crawl_folder import crawl_folder
    from worker.activities.extract_content import extract_content
    from worker.activities.chunk_content import chunk_content
    from worker.activities.generate_embeddings import generate_embeddings
    from worker.activities.generate_questions import generate_questions
    from worker.activities.index_chunks import index_chunks
    from worker.activities.update_project import update_project
    from worker.activities.refresh_token import refresh_google_token

logger = logging.getLogger(__name__)

# Retry policy for activities that don't hit external auth (chunking, embedding, etc.)
_DEFAULT_RETRY = RetryPolicy(maximum_attempts=3)

# No retries for auth-dependent activities — they raise non-retryable on 401
_AUTH_RETRY = RetryPolicy(maximum_attempts=1)


def _is_token_expired(error: ActivityError) -> bool:
    """Check whether an ActivityError was caused by an expired Google token."""
    return (
        isinstance(error.cause, ApplicationError)
        and error.cause.type == "TOKEN_EXPIRED"
    )


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

        try:
            return await self._run_pipeline(input)
        except ActivityError as e:
            return await self._handle_failure(input, e)
        except Exception as e:
            return await self._handle_failure(input, e)

    async def _run_pipeline(self, input: SyncInput) -> dict:
        """Execute the full sync pipeline with token refresh support."""

        # Step 0: Refresh the access token to handle stale-token-on-replay
        access_token = await self._refresh_token(input.user_refresh_token)

        # Step 1: Crawl folder to discover all files
        files = await workflow.execute_activity(
            crawl_folder,
            args=[input.folder_id, access_token],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=_AUTH_RETRY,
        )

        workflow.logger.info("Discovered %d files in folder %s", len(files), input.folder_id)

        # Persist total file count to DB
        await workflow.execute_activity(
            update_project,
            args=[input.project_id, {"files_total": len(files), "files_processed": 0}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        if not files:
            await workflow.execute_activity(
                update_project,
                args=[input.project_id, {
                    "sync_status": "COMPLETED",
                    "last_synced_at": "__now__",
                }],
                start_to_close_timeout=timedelta(seconds=30),
            )
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
        processed_count = 0

        for idx, file_info in enumerate(files, 1):
            file_name = file_info.get("name", "unknown")
            workflow.logger.info(
                "[WORKFLOW] Processing file %d/%d: %s (type=%s)",
                idx, len(files), file_name, file_info.get("mimeType"),
            )
            try:
                extracted = await self._extract_with_refresh(
                    file_info, access_token, input.user_refresh_token,
                )
                # _extract_with_refresh may have refreshed the token
                # Update our local copy (returned as second element if refreshed)
                if isinstance(extracted, tuple):
                    extracted, access_token = extracted

                # Skip files with no extractable text
                if not extracted or not extracted.get("text", "").strip():
                    workflow.logger.info(
                        "[WORKFLOW] Skipping file %s (no text extracted)", file_name,
                    )
                    continue

                # 2b. Chunk the extracted content
                chunks = await workflow.execute_activity(
                    chunk_content,
                    args=[extracted, file_info],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )

                if not chunks:
                    continue

                # 2c. Generate embeddings for chunks
                chunks_with_embeddings = await workflow.execute_activity(
                    generate_embeddings,
                    args=[chunks],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=_DEFAULT_RETRY,
                )

                # 2d. Generate hypothetical questions and their embeddings
                chunks_with_questions = await workflow.execute_activity(
                    generate_questions,
                    args=[chunks_with_embeddings],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )

                all_chunks.extend(chunks_with_questions)

                processed_count += 1
                workflow.logger.info(
                    "[WORKFLOW] File %s processed OK (%d chunks). Progress: %d/%d",
                    file_name, len(chunks_with_questions), processed_count, len(files),
                )
                await workflow.execute_activity(
                    update_project,
                    args=[input.project_id, {"files_processed": processed_count}],
                    start_to_close_timeout=timedelta(seconds=30),
                )

            except ActivityError as e:
                if _is_token_expired(e):
                    # Auth failed even after refresh — abort the entire pipeline
                    raise
                failed_count += 1
                workflow.logger.error(
                    "[WORKFLOW] FAILED to process file %s: %s: %s",
                    file_name, type(e).__name__, str(e),
                )
                continue

            except Exception as e:
                failed_count += 1
                workflow.logger.error(
                    "[WORKFLOW] FAILED to process file %s: %s: %s",
                    file_name, type(e).__name__, str(e),
                )
                continue

        # Step 3: Batch index all processed chunks
        workflow.logger.info(
            "[WORKFLOW] File processing done. processed=%d, failed=%d, total_chunks=%d",
            processed_count, failed_count, len(all_chunks),
        )
        indexed_count = 0
        if all_chunks:
            batch_size = 500
            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i : i + batch_size]
                result = await workflow.execute_activity(
                    index_chunks,
                    args=[batch, input.project_id],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=_DEFAULT_RETRY,
                )
                indexed_count += result.get("indexed", 0)

        # Mark project as completed in the database
        await workflow.execute_activity(
            update_project,
            args=[input.project_id, {
                "sync_status": "COMPLETED",
                "files_processed": processed_count,
                "last_synced_at": "__now__",
            }],
            start_to_close_timeout=timedelta(seconds=30),
        )

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

    async def _refresh_token(self, refresh_token: str) -> str:
        """Call the refresh_google_token activity to get a fresh access token."""
        return await workflow.execute_activity(
            refresh_google_token,
            args=[refresh_token],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_AUTH_RETRY,
        )

    async def _extract_with_refresh(
        self,
        file_info: dict,
        access_token: str,
        refresh_token: str,
    ) -> dict | tuple[dict, str]:
        """Extract content, retrying once with a refreshed token on 401.

        Returns either the extracted dict, or a (extracted, new_token) tuple
        if the token was refreshed mid-pipeline.
        """
        try:
            result = await workflow.execute_activity(
                extract_content,
                args=[file_info, access_token],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_AUTH_RETRY,
            )
            return result
        except ActivityError as e:
            if not _is_token_expired(e):
                raise

            # Token expired mid-pipeline — try refreshing once
            workflow.logger.info("[WORKFLOW] Token expired during extraction, refreshing...")
            new_token = await self._refresh_token(refresh_token)
            result = await workflow.execute_activity(
                extract_content,
                args=[file_info, new_token],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_AUTH_RETRY,
            )
            return (result, new_token)

    async def _handle_failure(self, input: SyncInput, error: Exception) -> dict:
        """Mark the project as FAILED with a user-friendly error message."""
        if isinstance(error, ActivityError) and _is_token_expired(error):
            error_msg = (
                "Your Google Drive authorization has expired. "
                "Please sign in again and re-sync your folder."
            )
        else:
            error_msg = f"Sync failed: {type(error).__name__}: {str(error)}"

        workflow.logger.error(
            "[WORKFLOW] Pipeline failed for project=%s: %s",
            input.project_id, error_msg,
        )

        try:
            await workflow.execute_activity(
                update_project,
                args=[input.project_id, {
                    "sync_status": "FAILED",
                    "sync_error": error_msg,
                }],
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception as db_err:
            workflow.logger.error(
                "[WORKFLOW] Could not update project status to FAILED: %s", db_err,
            )

        return {
            "project_id": input.project_id,
            "folder_id": input.folder_id,
            "total_files": 0,
            "processed_files": 0,
            "failed_files": 0,
            "indexed_chunks": 0,
            "error": error_msg,
        }
