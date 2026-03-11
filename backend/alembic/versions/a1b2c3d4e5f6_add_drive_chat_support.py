"""add drive chat support

Revision ID: a1b2c3d4e5f6
Revises: 7333ef8eb49b
Create Date: 2026-03-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "7333ef8eb49b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the agenttype enum
    agenttype_enum = sa.Enum("RAG", "DRIVE", name="agenttype")
    agenttype_enum.create(op.get_bind(), checkfirst=True)

    # Add agent_type column with default RAG
    op.add_column(
        "chat_sessions",
        sa.Column(
            "agent_type",
            sa.Enum("RAG", "DRIVE", name="agenttype"),
            nullable=False,
            server_default="RAG",
        ),
    )

    # Add user_id column (nullable for now, backfilled below)
    op.add_column(
        "chat_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_sessions_user_id",
        "chat_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_chat_sessions_user_id"),
        "chat_sessions",
        ["user_id"],
    )

    # Add gdrive_folder_id column
    op.add_column(
        "chat_sessions",
        sa.Column("gdrive_folder_id", sa.String(255), nullable=True),
    )

    # Make project_id nullable (Drive sessions have no project)
    op.alter_column(
        "chat_sessions",
        "project_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )

    # Backfill user_id for existing RAG sessions from their parent project
    op.execute(
        "UPDATE chat_sessions SET user_id = "
        "(SELECT user_id FROM projects WHERE projects.id = chat_sessions.project_id) "
        "WHERE project_id IS NOT NULL"
    )


def downgrade() -> None:
    # Drop new columns
    op.drop_index(op.f("ix_chat_sessions_user_id"), table_name="chat_sessions")
    op.drop_constraint(
        "fk_chat_sessions_user_id", "chat_sessions", type_="foreignkey"
    )
    op.drop_column("chat_sessions", "gdrive_folder_id")
    op.drop_column("chat_sessions", "user_id")
    op.drop_column("chat_sessions", "agent_type")

    # Make project_id non-nullable again
    op.alter_column(
        "chat_sessions",
        "project_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )

    # Drop the enum type
    sa.Enum(name="agenttype").drop(op.get_bind(), checkfirst=True)
