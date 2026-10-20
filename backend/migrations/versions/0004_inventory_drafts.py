"""Личные черновики поступлений и выдач, добавочная forward-миграция."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_inventory_drafts"
down_revision = "0003_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("posted_document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "document_type IN ('receipt', 'issue')", name=op.f("ck_inventory_drafts_valid_type")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'posted', 'archived')",
            name=op.f("ck_inventory_drafts_valid_status"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_inventory_drafts_positive_version")),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name=op.f("ck_inventory_drafts_object_payload")
        ),
        sa.CheckConstraint(
            "(status = 'posted') = (posted_document_id IS NOT NULL)",
            name=op.f("ck_inventory_drafts_posted_document_required"),
        ),
        sa.CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)",
            name=op.f("ck_inventory_drafts_archive_timestamp_required"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_drafts_owner_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["posted_document_id"],
            ["inventory_documents.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_drafts_posted_document_id_inventory_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_drafts")),
        sa.UniqueConstraint(
            "posted_document_id", name=op.f("uq_inventory_drafts_posted_document_id")
        ),
    )
    op.create_index("ix_inventory_drafts_owner_id", "inventory_drafts", ["owner_id"])
    op.create_index(
        "ix_inventory_drafts_owner_status_updated",
        "inventory_drafts",
        ["owner_id", "status", "updated_at", "id"],
    )


def downgrade() -> None:
    raise RuntimeError("Разрешены только forward-миграции; откат схемы запрещён.")
