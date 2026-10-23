import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin


class EquipmentInstance(RecordMixin, Base):
    __tablename__ = "equipment_instances"
    __table_args__ = (
        CheckConstraint("length(btrim(serial_number)) > 0", name="serial_number_not_blank"),
        CheckConstraint("length(btrim(inventory_number)) > 0", name="inventory_number_not_blank"),
        Index("ix_equipment_instances_active_item", "archived_at", "inventory_item_id"),
        Index("ix_equipment_instances_active_status", "archived_at", "is_under_repair"),
        Index(
            "uq_equipment_instances_inventory_number_key",
            "inventory_number_key",
            unique=True,
            postgresql_where="inventory_number_key IS NOT NULL",
        ),
        Index(
            "uq_equipment_instances_manufacturer_serial_key",
            "manufacturer_id",
            "serial_number_key",
            unique=True,
            postgresql_where="serial_number_key IS NOT NULL",
        ),
    )

    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"), index=True
    )
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manufacturers.id", ondelete="RESTRICT"), index=True
    )
    serial_number: Mapped[str | None] = mapped_column(String(200))
    serial_number_key: Mapped[str | None] = mapped_column(String(200))
    inventory_number: Mapped[str | None] = mapped_column(String(200))
    inventory_number_key: Mapped[str | None] = mapped_column(String(200))
    current_building: Mapped[str | None] = mapped_column(String(200))
    current_room: Mapped[str | None] = mapped_column(String(100))
    current_department: Mapped[str | None] = mapped_column(String(200))
    current_recipient: Mapped[str | None] = mapped_column(String(300))
    is_under_repair: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    version: Mapped[int] = mapped_column(default=1, server_default="1")
