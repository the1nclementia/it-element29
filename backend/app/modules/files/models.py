import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FileAttachment(Base):
    __tablename__ = "file_attachments"
    __table_args__ = (
        CheckConstraint("size > 0 AND width > 0 AND height > 0", name="positive_dimensions"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int]
    height: Mapped[int]
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryItemAttachment(Base):
    __tablename__ = "inventory_item_attachments"
    __table_args__ = (
        UniqueConstraint("inventory_item_id", "file_attachment_id"),
        CheckConstraint("position >= 0", name="valid_position"),
        Index(
            "uq_inventory_item_attachments_active_primary",
            "inventory_item_id",
            unique=True,
            postgresql_where=text("is_primary AND archived_at IS NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"), index=True
    )
    file_attachment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("file_attachments.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(default=0, server_default="0")
    is_primary: Mapped[bool] = mapped_column(default=False, server_default="false")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
