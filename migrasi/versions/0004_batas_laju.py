"""batas_laju: pembatasan laju per IP yang tahan restart

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batas_laju",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kunci", sa.String(64), nullable=False),
        sa.Column("aksi", sa.String(20), nullable=False),
        sa.Column("waktu", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_batas_laju_kunci", "batas_laju", ["kunci"])
    op.create_index("ix_batas_laju_waktu", "batas_laju", ["waktu"])


def downgrade() -> None:
    op.drop_index("ix_batas_laju_waktu", table_name="batas_laju")
    op.drop_index("ix_batas_laju_kunci", table_name="batas_laju")
    op.drop_table("batas_laju")
