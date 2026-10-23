"""Режимы номенклатуры и физические экземпляры оборудования."""

import sqlalchemy as sa
from alembic import op

revision = "0007_equipment_instances"
down_revision = "0006_recipient_building"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column("accounting_mode", sa.String(20), server_default="quantity", nullable=False),
    )
    op.add_column(
        "inventory_items",
        sa.Column("item_type", sa.String(30), server_default="cartridge", nullable=False),
    )
    op.create_check_constraint(
        "valid_accounting_mode", "inventory_items", "accounting_mode IN ('quantity','serialized')"
    )
    op.create_check_constraint(
        "valid_item_type",
        "inventory_items",
        "item_type IN ('cartridge','consumable','monitor','computer','printer')",
    )
    op.create_check_constraint(
        "serialized_equipment_type",
        "inventory_items",
        "accounting_mode <> 'serialized' OR item_type IN ('monitor','computer','printer')",
    )
    op.create_table(
        "equipment_instances",
        sa.Column("inventory_item_id", sa.Uuid(), nullable=False),
        sa.Column("manufacturer_id", sa.Uuid(), nullable=False),
        sa.Column("serial_number", sa.String(200), nullable=True),
        sa.Column("serial_number_key", sa.String(200), nullable=True),
        sa.Column("inventory_number", sa.String(200), nullable=True),
        sa.Column("inventory_number_key", sa.String(200), nullable=True),
        sa.Column("current_building", sa.String(200), nullable=True),
        sa.Column("current_room", sa.String(100), nullable=True),
        sa.Column("current_department", sa.String(200), nullable=True),
        sa.Column("current_recipient", sa.String(300), nullable=True),
        sa.Column("is_under_repair", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "serial_number IS NULL OR length(btrim(serial_number)) > 0",
            name="serial_number_not_blank",
        ),
        sa.CheckConstraint(
            "inventory_number IS NULL OR length(btrim(inventory_number)) > 0",
            name="inventory_number_not_blank",
        ),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["manufacturer_id"], ["manufacturers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_equipment_instances_inventory_item_id", "equipment_instances", ["inventory_item_id"]
    )
    op.create_index(
        "ix_equipment_instances_manufacturer_id", "equipment_instances", ["manufacturer_id"]
    )
    op.create_index(
        "ix_equipment_instances_active_item",
        "equipment_instances",
        ["archived_at", "inventory_item_id"],
    )
    op.create_index(
        "ix_equipment_instances_active_status",
        "equipment_instances",
        ["archived_at", "is_under_repair"],
    )
    op.create_index(
        "uq_equipment_instances_inventory_number_key",
        "equipment_instances",
        ["inventory_number_key"],
        unique=True,
        postgresql_where=sa.text("inventory_number_key IS NOT NULL"),
    )
    op.create_index(
        "uq_equipment_instances_manufacturer_serial_key",
        "equipment_instances",
        ["manufacturer_id", "serial_number_key"],
        unique=True,
        postgresql_where=sa.text("serial_number_key IS NOT NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Разрешены только forward-миграции; откат схемы запрещён.")
