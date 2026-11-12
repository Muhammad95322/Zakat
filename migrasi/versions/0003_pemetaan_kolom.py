"""pemetaan_kolom: pemetaan kolom berkas per lembaga (wizard impor)

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pemetaan_kolom",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("tanda_kolom", sa.String(64), nullable=False),
        sa.Column("pemetaan", sa.JSON(), nullable=False),
        sa.Column("dibuat_oleh", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "tanda_kolom", name="uq_pemetaan_kolom_tenant_tanda"),
    )
    op.create_index("ix_pemetaan_kolom_tenant_id", "pemetaan_kolom", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_pemetaan_kolom_tenant_id", table_name="pemetaan_kolom")
    op.drop_table("pemetaan_kolom")
