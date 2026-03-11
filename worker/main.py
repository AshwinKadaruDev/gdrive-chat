"""Temporal worker entry point for Talk-to-a-Folder sync pipeline."""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

# Ensure the project root is on sys.path so worker.* imports work
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
# Also add backend/ so that `from app.models...` imports work (used by update_project)
sys.path.insert(0, os.path.join(_project_root, "backend"))

from worker.activities.crawl_folder import crawl_folder
from worker.activities.extract_content import extract_content
from worker.activities.chunk_content import chunk_content
from worker.activities.generate_embeddings import generate_embeddings
from worker.activities.generate_questions import generate_questions
from worker.activities.index_chunks import index_chunks
from worker.activities.update_project import update_project
from worker.activities.refresh_token import refresh_google_token
from worker.workflows.sync_folder import SyncFolderWorkflow

TASK_QUEUE = "talk-to-folder-sync"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    """Connect to Temporal and start the worker."""
    temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    # Retry connection — Temporal may still be starting up
    max_retries = 15
    client = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Connecting to Temporal at %s (namespace=%s, attempt %d/%d)...",
                        temporal_host, temporal_namespace, attempt, max_retries)
            client = await Client.connect(temporal_host, namespace=temporal_namespace)
            break
        except RuntimeError:
            if attempt == max_retries:
                logger.error("Could not connect to Temporal after %d attempts. Is Temporal running?", max_retries)
                raise
            logger.warning("Temporal not ready, retrying in 3s...")
            await asyncio.sleep(3)

    logger.info("Starting worker on task queue '%s'...", TASK_QUEUE)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[SyncFolderWorkflow],
        activities=[
            crawl_folder,
            extract_content,
            chunk_content,
            generate_embeddings,
            generate_questions,
            index_chunks,
            update_project,
            refresh_google_token,
        ],
    )

    logger.info("Worker is running. Press Ctrl+C to stop.")
    await worker.run()


def main() -> None:
    """Entry point."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped.")


if __name__ == "__main__":
    main()
