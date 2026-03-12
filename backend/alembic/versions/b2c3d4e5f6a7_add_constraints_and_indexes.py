"""add constraints and indexes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill NULL user_ids from project ownership
    op.execute(
        """
        UPDATE chat_sessions
        SET user_id = (
            SELECT user_id FROM projects WHERE projects.id = chat_sessions.project_id
        )
        WHERE user_id IS NULL AND project_id IS NOT NULL
        """
    )
    # Delete truly orphaned sessions (no user_id and no project_id)
    op.execute("DELETE FROM chat_sessions WHERE user_id IS NULL")

    # Make user_id non-nullable
    op.alter_column("chat_sessions", "user_id", nullable=False)

    # Unique constraint: one project per user+folder
    op.create_unique_constraint(
        "uq_projects_user_folder", "projects", ["user_id", "gdrive_folder_id"]
    )

    # Performance indexes
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_index("ix_chat_sessions_created_at", "chat_sessions", ["created_at"])
    op.create_index("ix_projects_sync_status", "projects", ["sync_status"])


def downgrade() -> None:
    op.drop_index("ix_projects_sync_status", table_name="projects")
    op.drop_index("ix_chat_sessions_created_at", table_name="chat_sessions")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_constraint("uq_projects_user_folder", "projects", type_="unique")
    op.alter_column("chat_sessions", "user_id", nullable=True)
