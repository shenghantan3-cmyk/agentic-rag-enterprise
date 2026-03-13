"""add structured citations payload

Revision ID: 0002_citations_payload
Revises: 0001_init
Create Date: 2026-03-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_citations_payload"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("citations_payload_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "citations_payload_json")
