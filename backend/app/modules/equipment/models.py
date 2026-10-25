import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin


class EquipmentInstance(RecordMixin, Base):
    __tablename__ = "equipment_instances"
    __table_args__ = (
        CheckConstraint("length(btrim(serial_number)) > 0", name="serial_number_not_blank"),
        CheckConstraint("length(btrim(inventory_number)) > 0", name="inventory_number_not_blank"),
        Index("ix_equipment_instances_active_item", "archived_at", "inventory_item_id"),
        Index("ix_equipment_instances_active_status", "archived_at", "is_under_repair"),
        Index("ix_equipment_instances_inventory_number_key", "inventory_number_key"),
        Index(
            "uq_equipment_instances_inventory_number_key",
            "inventory_number_key",
            unique=True,
            postgresql_where=(
                "inventory_number_key IS NOT NULL AND btrim(inventory_number_key) <> ''"
            ),
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


class EquipmentMovement(Base):
    __tablename__ = "equipment_movements"
    __table_args__ = (
        UniqueConstraint("document_id", "equipment_instance_id", "movement_type"),
        CheckConstraint(
            "movement_type IN ('receipt','issue','return','replacement','transfer')",
            name="valid_movement_type",
        ),
        Index("ix_equipment_movements_instance_time", "equipment_instance_id", "occurred_at", "id"),
        Index("ix_equipment_movements_document_id", "document_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    equipment_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment_instances.id", ondelete="RESTRICT")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_documents.id", ondelete="RESTRICT")
    )
    movement_type: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    before_building: Mapped[str | None] = mapped_column(String(200))
    before_room: Mapped[str | None] = mapped_column(String(100))
    before_department: Mapped[str | None] = mapped_column(String(200))
    before_recipient: Mapped[str | None] = mapped_column(String(300))
    after_building: Mapped[str | None] = mapped_column(String(200))
    after_room: Mapped[str | None] = mapped_column(String(100))
    after_department: Mapped[str | None] = mapped_column(String(200))
    after_recipient: Mapped[str | None] = mapped_column(String(300))
