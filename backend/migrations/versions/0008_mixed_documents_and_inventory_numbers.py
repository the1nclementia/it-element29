"""Расширение типов документов и снятие уникальности инвентарного номера."""

import sqlalchemy as sa
from alembic import op

revision = "0008_mixed_documents_and_inventory_numbers"
down_revision = "0007_equipment_instances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The operation is transactional on PostgreSQL: both constraints and the
    # legacy inventory-number index change together with the Alembic revision.
    op.drop_constraint(
        op.f("ck_inventory_documents_valid_type"), "inventory_documents", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inventory_documents_valid_type"),
        "inventory_documents",
        "document_type IN ('receipt','issue','reversal','return','replacement','transfer')",
    )
    op.drop_constraint(op.f("ck_inventory_drafts_valid_type"), "inventory_drafts", type_="check")
    op.create_check_constraint(
        op.f("ck_inventory_drafts_valid_type"),
        "inventory_drafts",
        "document_type IN ('receipt','issue','return','replacement','transfer')",
    )
    op.drop_index("uq_equipment_instances_inventory_number_key", table_name="equipment_instances")
    op.create_index(
        "ix_equipment_instances_inventory_number_key",
        "equipment_instances",
        ["inventory_number_key"],
    )
    op.create_table(
        "inventory_document_equipment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("equipment_instance_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("internal_code", sa.String(50), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("manufacturer", sa.String(200), nullable=False),
        sa.Column("serial_number", sa.String(200), nullable=True),
        sa.Column("inventory_number", sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["inventory_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["equipment_instance_id"], ["equipment_instances.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "equipment_instance_id",
            name="uq_inventory_document_equipment_document_instance",
        ),
        sa.UniqueConstraint(
            "document_id", "line_number", name="uq_inventory_document_equipment_document_line"
        ),
    )
    op.create_index(
        "ix_inventory_document_equipment_document_id",
        "inventory_document_equipment",
        ["document_id"],
    )
    op.create_index(
        "ix_inventory_document_equipment_instance_id",
        "inventory_document_equipment",
        ["equipment_instance_id"],
    )
    op.create_table(
        "equipment_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("equipment_instance_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("movement_type", sa.String(30), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("before_building", sa.String(200), nullable=True),
        sa.Column("before_room", sa.String(100), nullable=True),
        sa.Column("before_department", sa.String(200), nullable=True),
        sa.Column("before_recipient", sa.String(300), nullable=True),
        sa.Column("after_building", sa.String(200), nullable=True),
        sa.Column("after_room", sa.String(100), nullable=True),
        sa.Column("after_department", sa.String(200), nullable=True),
        sa.Column("after_recipient", sa.String(300), nullable=True),
        sa.ForeignKeyConstraint(
            ["equipment_instance_id"], ["equipment_instances.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["inventory_documents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "equipment_instance_id", "movement_type"),
        sa.CheckConstraint(
            "movement_type IN ('receipt','issue','return','replacement','transfer')",
            name=op.f("ck_equipment_movements_valid_movement_type"),
        ),
    )
    op.create_index(
        "ix_equipment_movements_instance_time",
        "equipment_movements",
        ["equipment_instance_id", "occurred_at", "id"],
    )
    op.create_index("ix_equipment_movements_document_id", "equipment_movements", ["document_id"])


def downgrade() -> None:
    raise RuntimeError("Разрешены только forward-миграции; откат схемы запрещён.")
