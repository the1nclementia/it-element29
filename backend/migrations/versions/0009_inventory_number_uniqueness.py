"""Восстановление уникальности непустых инвентарных номеров."""

import sqlalchemy as sa
from alembic import op

revision = "0009_inventory_number_uniqueness"
down_revision = "0008_mixed_documents_and_inventory_numbers"
branch_labels = None
depends_on = None


def duplicate_inventory_number_keys(rows):
    """Return normalized non-empty keys that would violate the unique index."""
    return [
        (str(row["inventory_number_key"]), int(row["duplicate_count"]))
        for row in rows
        if row["inventory_number_key"] and int(row["duplicate_count"]) > 1
    ]


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT inventory_number_key, count(*) AS duplicate_count
            FROM equipment_instances
            WHERE inventory_number_key IS NOT NULL
              AND btrim(inventory_number_key) <> ''
            GROUP BY inventory_number_key
            HAVING count(*) > 1
            ORDER BY inventory_number_key
            """
        )
    ).mappings()
    duplicates = duplicate_inventory_number_keys(rows)
    if duplicates:
        details = ", ".join(f"{key} ({count})" for key, count in duplicates[:20])
        suffix = "" if len(duplicates) <= 20 else "; показаны первые 20"
        raise RuntimeError(
            "Невозможно восстановить уникальность инвентарных номеров: "
            f"найдены дубликаты {details}{suffix}. "
            "Исправьте данные вручную и повторите миграцию."
        )
    op.create_index(
        "uq_equipment_instances_inventory_number_key",
        "equipment_instances",
        ["inventory_number_key"],
        unique=True,
        postgresql_where=sa.text(
            "inventory_number_key IS NOT NULL AND btrim(inventory_number_key) <> ''"
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Разрешены только forward-миграции; откат схемы запрещён.")
