"""Личные изменяемые черновики отделены от неизменяемых складских документов."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin


class InventoryDraft(RecordMixin, Base):
    __tablename__ = "inventory_drafts"
    __table_args__ = (
        CheckConstraint("document_type IN ('receipt', 'issue')", name="valid_type"),
        CheckConstraint("status IN ('draft', 'posted', 'archived')", name="valid_status"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="object_payload"),
        CheckConstraint(
            "(status = 'posted') = (posted_document_id IS NOT NULL)",
            name="posted_document_required",
        ),
        CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)", name="archive_timestamp_required"
        ),
        Index("ix_inventory_drafts_owner_status_updated", "owner_id", "status", "updated_at", "id"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    document_type: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    posted_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inventory_documents.id", ondelete="RESTRICT"), unique=True
    )
