import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin

inventory_document_number_seq = Sequence("inventory_document_number_seq", metadata=Base.metadata)
inventory_category_code_seq = Sequence("inventory_category_code_seq", metadata=Base.metadata)
inventory_item_code_seq = Sequence("inventory_item_code_seq", metadata=Base.metadata)


class Manufacturer(RecordMixin, Base):
    __tablename__ = "manufacturers"
    __table_args__ = (CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),)
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200), unique=True)
    version: Mapped[int] = mapped_column(default=1, server_default="1")


class InventoryCategory(RecordMixin, Base):
    __tablename__ = "inventory_categories"
    __table_args__ = (
        CheckConstraint("length(btrim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
    )
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(default=1, server_default="1")


class PrinterModel(RecordMixin, Base):
    __tablename__ = "printer_models"
    __table_args__ = (
        UniqueConstraint("manufacturer_id", "model_key"),
        CheckConstraint("length(btrim(model)) > 0", name="model_not_blank"),
    )
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manufacturers.id", ondelete="RESTRICT"), index=True
    )
    model: Mapped[str] = mapped_column(String(200))
    model_key: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(default=1, server_default="1")


class InventoryItem(RecordMixin, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint("min_stock >= 0 AND min_stock <= 9007199254740991", name="valid_min_stock"),
        CheckConstraint(
            "accounting_mode IN ('quantity', 'serialized')", name="valid_accounting_mode"
        ),
        CheckConstraint(
            "item_type IN ('cartridge', 'consumable', 'monitor', 'computer', 'printer')",
            name="valid_item_type",
        ),
        CheckConstraint(
            "accounting_mode <> 'serialized' OR item_type IN ('monitor', 'computer', 'printer')",
            name="serialized_equipment_type",
        ),
        CheckConstraint("length(btrim(internal_code)) > 0", name="code_not_blank"),
        CheckConstraint("length(btrim(model)) > 0", name="model_not_blank"),
        Index("ix_inventory_items_archived_at_internal_code", "archived_at", "internal_code"),
        Index("ix_inventory_items_model", "model"),
    )
    internal_code: Mapped[str] = mapped_column(String(50), unique=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_categories.id", ondelete="RESTRICT"), index=True
    )
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manufacturers.id", ondelete="RESTRICT"), index=True
    )
    model: Mapped[str] = mapped_column(String(200))
    article: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    min_stock: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    accounting_mode: Mapped[str] = mapped_column(
        String(20), default="quantity", server_default="quantity"
    )
    item_type: Mapped[str] = mapped_column(
        String(30), default="cartridge", server_default="cartridge"
    )
    version: Mapped[int] = mapped_column(default=1, server_default="1")


class InventoryCompatibility(Base):
    __tablename__ = "inventory_compatibilities"
    __table_args__ = (UniqueConstraint("inventory_item_id", "printer_model_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"), index=True
    )
    printer_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("printer_models.id", ondelete="RESTRICT"), index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryDocument(Base):
    __tablename__ = "inventory_documents"
    __table_args__ = (
        UniqueConstraint("created_by_id", "document_type", "idempotency_key"),
        CheckConstraint(
            "document_type IN ('receipt','issue','reversal','return','replacement','transfer')",
            name="valid_type",
        ),
        CheckConstraint(
            "receipt_purpose IS NULL OR receipt_purpose IN ('delivery','opening_balance')",
            name="valid_receipt_purpose",
        ),
        Index("ix_inventory_documents_created_at_id", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    document_type: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document_date: Mapped[date] = mapped_column(Date, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    recipient_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    recipient_name: Mapped[str | None] = mapped_column(String(300))
    recipient_building: Mapped[str | None] = mapped_column(String(200))
    recipient_personnel_number: Mapped[str | None] = mapped_column(String(50))
    recipient_department: Mapped[str | None] = mapped_column(String(200))
    recipient_room: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str] = mapped_column(Text, default="", server_default="")
    receipt_purpose: Mapped[str | None] = mapped_column(String(30))
    external_number: Mapped[str | None] = mapped_column(String(100))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inventory_documents.id", ondelete="RESTRICT"), unique=True
    )
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[uuid.UUID]
    request_hash: Mapped[str] = mapped_column(String(64))


class InventoryDocumentItem(Base):
    __tablename__ = "inventory_document_items"
    __table_args__ = (
        UniqueConstraint("document_id", "inventory_item_id"),
        UniqueConstraint(
            "document_id", "line_number", name="uq_inventory_document_items_document_line"
        ),
        UniqueConstraint("id", "inventory_item_id"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("line_number > 0", name="positive_line_number"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_documents.id", ondelete="RESTRICT"), index=True
    )
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[int] = mapped_column(BigInteger)
    line_number: Mapped[int]
    internal_code: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    manufacturer: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(10), default="pcs", server_default="pcs")


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_item_id", "inventory_item_id"],
            ["inventory_document_items.id", "inventory_document_items.inventory_item_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("delta <> 0", name="nonzero_delta"),
        Index("ix_inventory_movements_item_time_id", "inventory_item_id", "occurred_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_item_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"), index=True
    )
    delta: Mapped[int] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inventory_movements.id", ondelete="RESTRICT"), unique=True
    )
