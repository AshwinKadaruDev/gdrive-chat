"""Activity: update project fields in the database from the Temporal worker."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from temporalio import activity

logger = logging.getLogger(__name__)


def _get_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/talk_to_folder",
    )


@activity.defn
async def update_project(project_id: str, fields: dict) -> None:
    """Update one or more columns on a Project row.

    Accepted keys in *fields*:
        files_total, files_processed, sync_status, sync_error, last_synced_at
    """
    from app.models.project import Project

    activity.logger.info("[DB-UPDATE] Called for project=%s fields=%s", project_id, fields)

    allowed = {"files_total", "files_processed", "sync_status", "sync_error", "last_synced_at"}
    values = {k: v for k, v in fields.items() if k in allowed}
    if not values:
        activity.logger.warning("[DB-UPDATE] No allowed fields to update, skipping")
        return

    # Handle last_synced_at sentinel
    if values.get("last_synced_at") == "__now__":
        values["last_synced_at"] = datetime.now(timezone.utc)

    db_url = _get_database_url()
    activity.logger.info("[DB-UPDATE] Connecting to DB: %s", db_url.split("@")[-1] if "@" in db_url else "<hidden>")

    try:
        engine = create_async_engine(db_url, echo=False)
        async with AsyncSession(engine) as session:
            stmt = update(Project).where(Project.id == project_id).values(**values)
            result = await session.execute(stmt)
            activity.logger.info(
                "[DB-UPDATE] UPDATE executed: rowcount=%d for project=%s",
                result.rowcount, project_id,
            )
            await session.commit()
        await engine.dispose()
        activity.logger.info("[DB-UPDATE] Successfully updated project %s: %s", project_id, values)
    except Exception as exc:
        activity.logger.error(
            "[DB-UPDATE] FAILED to update project %s: %s: %s",
            project_id, type(exc).__name__, exc,
            exc_info=True,
        )
        raise
