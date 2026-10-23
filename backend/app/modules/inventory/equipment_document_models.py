import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InventoryDocumentEquipment(Base):
    __tablename__ = "inventory_document_equipment"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "equipment_instance_id",
            name="uq_inventory_document_equipment_document_instance",
        ),
        UniqueConstraint(
            "document_id", "line_number", name="uq_inventory_document_equipment_document_line"
        ),
        Index("ix_inventory_document_equipment_document_id", "document_id"),
        Index("ix_inventory_document_equipment_instance_id", "equipment_instance_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_documents.id", ondelete="RESTRICT")
    )
    equipment_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment_instances.id", ondelete="RESTRICT")
    )
    line_number: Mapped[int]
    internal_code: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    manufacturer: Mapped[str] = mapped_column(String(200))
    serial_number: Mapped[str | None] = mapped_column(String(200))
    inventory_number: Mapped[str | None] = mapped_column(String(200))
