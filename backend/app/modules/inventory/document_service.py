"""Read-only projections of immutable warehouse documents and movements."""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.modules.identity.errors import fail
from app.modules.identity.models import User
from app.modules.inventory.models import (
    InventoryDocument,
    InventoryDocumentItem,
    InventoryItem,
    InventoryMovement,
)


def document_response(session: Session, document: InventoryDocument) -> dict:
    reversal = session.scalar(
        select(InventoryDocument).where(InventoryDocument.reversal_of_id == document.id)
    )
    result = {
        name: getattr(document, name)
        for name in (
            "id",
            "number",
            "document_type",
            "document_date",
            "created_at",
            "created_by_id",
            "recipient_employee_id",
            "recipient_name",
            "recipient_personnel_number",
            "recipient_department",
            "recipient_room",
            "recipient_building",
            "comment",
            "receipt_purpose",
            "external_number",
            "supplier_name",
            "reversal_of_id",
            "reason",
        )
    }
    result.update(
        created_by_name=session.scalar(
            select(User.display_name).where(User.id == document.created_by_id)
        ),
        is_cancelled=reversal is not None,
        reversal_id=reversal.id if reversal else None,
        reversal_number=reversal.number if reversal else None,
        items=[
            {
                **{
                    name: getattr(line, name)
                    for name in (
                        "id",
                        "line_number",
                        "inventory_item_id",
                        "quantity",
                        "internal_code",
                        "model",
                        "manufacturer",
                        "unit",
                    )
                },
                "delta": delta,
            }
            for line, delta in session.execute(
                select(InventoryDocumentItem, InventoryMovement.delta)
                .join(
                    InventoryMovement,
                    InventoryMovement.document_item_id == InventoryDocumentItem.id,
                )
                .where(InventoryDocumentItem.document_id == document.id)
                .order_by(InventoryDocumentItem.line_number)
            )
        ],
    )
    return result


def get_document(session: Session, document_id: uuid.UUID) -> InventoryDocument:
    document = session.get(InventoryDocument, document_id)
    if document is None:
        fail(404, "document_not_found", "Документ не найден.")
    return document


def list_documents(
    session: Session,
    *,
    document_type: str | None,
    recipient_employee_id: uuid.UUID | None,
    created_by_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    cancelled: bool | None,
    offset: int,
    limit: int,
) -> dict:
    if date_from and date_to and date_from > date_to:
        fail(422, "invalid_date_range", "Начало периода должно быть не позднее окончания.")
    query = select(InventoryDocument)
    for name, value in (
        ("document_type", document_type),
        ("recipient_employee_id", recipient_employee_id),
        ("created_by_id", created_by_id),
    ):
        if value is not None:
            query = query.where(getattr(InventoryDocument, name) == value)
    if date_from:
        query = query.where(InventoryDocument.document_date >= date_from)
    if date_to:
        query = query.where(InventoryDocument.document_date <= date_to)
    if cancelled is not None:
        reversal = aliased(InventoryDocument)
        exists = select(reversal.id).where(reversal.reversal_of_id == InventoryDocument.id).exists()
        query = query.where(exists if cancelled else ~exists)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    documents = session.scalars(
        query.order_by(InventoryDocument.created_at.desc(), InventoryDocument.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return {"items": [document_response(session, row) for row in documents], "total": total}


def list_movements(session: Session, item_id: uuid.UUID, offset: int, limit: int) -> dict:
    if session.get(InventoryItem, item_id) is None:
        fail(404, "item_not_found", "Позиция не найдена.")
    query = (
        select(InventoryMovement, InventoryDocument)
        .join(InventoryDocumentItem, InventoryDocumentItem.id == InventoryMovement.document_item_id)
        .join(InventoryDocument, InventoryDocument.id == InventoryDocumentItem.document_id)
        .where(InventoryMovement.inventory_item_id == item_id)
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    return {
        "total": total,
        "items": [
            {
                "id": movement.id,
                "document_id": document.id,
                "document_number": document.number,
                "document_type": document.document_type,
                "delta": movement.delta,
                "occurred_at": movement.occurred_at,
                "reversal_of_id": movement.reversal_of_id,
            }
            for movement, document in session.execute(
                query.order_by(InventoryMovement.occurred_at.desc(), InventoryMovement.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ],
    }
