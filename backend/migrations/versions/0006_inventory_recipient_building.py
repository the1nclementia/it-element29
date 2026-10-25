"""Свободное здание в снимке получателя документа."""

import sqlalchemy as sa
from alembic import op

revision = "0006_recipient_building"
down_revision = "0005_inventory_document_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("inventory_category_code_seq")))
    op.execute(sa.schema.CreateSequence(sa.Sequence("inventory_item_code_seq")))
    op.add_column(
        "inventory_documents", sa.Column("recipient_building", sa.String(200), nullable=True)
    )


def downgrade() -> None:
    raise RuntimeError("Разрешены только forward-миграции; откат схемы запрещён.")
