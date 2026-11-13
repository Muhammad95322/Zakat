"""sesi_web: sesi login frontend web (cookie berisi ID acak, DB menyimpan hash-nya)

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sesi_web",
        sa.Column("id_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("refresh_token_id", sa.String(36), nullable=True),
        sa.Column("sesi_versi", sa.Integer(), nullable=False),
        sa.Column("csrf", sa.String(64), nullable=False),
        sa.Column("dibuat", sa.DateTime(), nullable=False),
        sa.Column("kedaluwarsa", sa.DateTime(), nullable=False),
        sa.Column("dicabut", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sesi_web_user_id", "sesi_web", ["user_id"])
    op.create_index("ix_sesi_web_kedaluwarsa", "sesi_web", ["kedaluwarsa"])


def downgrade() -> None:
    op.drop_index("ix_sesi_web_kedaluwarsa", table_name="sesi_web")
    op.drop_index("ix_sesi_web_user_id", table_name="sesi_web")
    op.drop_table("sesi_web")
