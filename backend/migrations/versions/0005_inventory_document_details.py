"""Необязательные снимки поставщика и кабинета в складских документах."""

import sqlalchemy as sa
from alembic import op

revision = "0005_inventory_document_details"
down_revision = "0004_inventory_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_documents", sa.Column("supplier_name", sa.String(200), nullable=True))
    op.add_column("inventory_documents", sa.Column("recipient_room", sa.String(100), nullable=True))


def downgrade() -> None:
    raise RuntimeError("Разрешены только forward-миграции; откат схемы запрещён.")
