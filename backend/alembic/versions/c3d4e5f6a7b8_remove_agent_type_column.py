"""remove agent_type column

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the agent_type column
    op.drop_column("chat_sessions", "agent_type")
    # Drop the enum type
    sa.Enum(name="agenttype").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Recreate the enum
    agenttype_enum = sa.Enum("RAG", "DRIVE", name="agenttype")
    agenttype_enum.create(op.get_bind(), checkfirst=True)
    # Re-add column with DRIVE default (all sessions were Drive at removal time)
    op.add_column(
        "chat_sessions",
        sa.Column(
            "agent_type",
            sa.Enum("RAG", "DRIVE", name="agenttype"),
            nullable=False,
            server_default="DRIVE",
        ),
    )
