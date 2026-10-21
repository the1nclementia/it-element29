"""Warehouse commands. Item row locks serialize every balance-changing operation."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.modules.directory.models import Department, Employee
from app.modules.identity.authorization import revalidate_mutation
from app.modules.identity.errors import fail
from app.modules.identity.models import User
from app.modules.identity.repository import audit
from app.modules.inventory.document_service import document_response, get_document
from app.modules.inventory.models import (
    InventoryDocument,
    InventoryDocumentItem,
    InventoryItem,
    InventoryMovement,
    Manufacturer,
    inventory_document_number_seq,
)
from app.modules.inventory.stock_schemas import IssueInput, ReceiptInput, ReversalInput

MAX_BALANCE = 9_007_199_254_740_991


def request_hash(payload: dict) -> str:
    normalized = dict(payload)
    # New optional metadata must not invalidate idempotency keys issued before 0005.
    for field in ("supplier_name", "recipient_room"):
        if normalized.get(field) is None:
            normalized.pop(field, None)
    if "items" in normalized:
        normalized["items"] = sorted(normalized["items"], key=lambda row: row["inventory_item_id"])
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def lock_command(session: Session, actor_id: uuid.UUID, kind: str, key: uuid.UUID) -> None:
    digest = hashlib.sha256(f"inventory:{actor_id}:{kind}:{key}".encode()).digest()
    lock_id = int.from_bytes(digest[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def replay(
    session: Session,
    actor: User,
    session_hash: str,
    kind: str,
    key: uuid.UUID,
    fingerprint: str,
    permission: str,
) -> dict | None:
    previous = session.scalar(
        select(InventoryDocument).where(
            InventoryDocument.created_by_id == actor.id,
            InventoryDocument.document_type == kind,
            InventoryDocument.idempotency_key == key,
        )
    )
    if previous is None:
        return None
    revalidate_mutation(session, actor, session_hash, permission)
    if previous.request_hash != fingerprint:
        fail(409, "idempotency_conflict", "Этот ключ уже использован для другого документа.")
    return document_response(session, previous)


def lock_recipient(session: Session, employee_id: uuid.UUID) -> tuple[Employee, Department]:
    department_id = session.scalar(select(Employee.department_id).where(Employee.id == employee_id))
    if department_id is None:
        fail(404, "employee_not_found", "Получатель не найден.")
    department = session.scalar(
        select(Department)
        .where(Department.id == department_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    employee = session.scalar(
        select(Employee)
        .where(Employee.id == employee_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if employee.department_id != department_id:
        fail(409, "recipient_changed", "Подразделение получателя изменилось. Повторите запрос.")
    if employee.archived_at or department.archived_at:
        fail(409, "recipient_archived", "Получатель или его подразделение архивированы.")
    return employee, department


def lock_items(session: Session, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, InventoryItem]:
    items = session.scalars(
        select(InventoryItem)
        .where(InventoryItem.id.in_(item_ids))
        .order_by(InventoryItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    result = {item.id: item for item in items}
    if len(result) != len(item_ids):
        fail(404, "item_not_found", "Одна из позиций не найдена. Обновите каталог.")
    return result


def check_balances(session: Session, deltas: dict[uuid.UUID, int]) -> None:
    # Separate statement AFTER locks: PostgreSQL READ COMMITTED gets the committed balance.
    balances = dict(
        session.execute(
            select(InventoryMovement.inventory_item_id, func.sum(InventoryMovement.delta))
            .where(InventoryMovement.inventory_item_id.in_(deltas))
            .group_by(InventoryMovement.inventory_item_id)
        ).all()
    )
    shortages = [
        {
            "inventory_item_id": str(item),
            "available": int(balances.get(item, 0)),
            "requested": -delta,
        }
        for item, delta in deltas.items()
        if balances.get(item, 0) + delta < 0
    ]
    if shortages:
        raise HTTPException(
            409,
            detail={
                "code": "insufficient_stock",
                "message": "Недостаточно остатка для проведения документа.",
                "items": shortages,
            },
        )
    if any(balances.get(item, 0) + delta > MAX_BALANCE for item, delta in deltas.items()):
        fail(409, "balance_limit", "Превышен допустимый остаток позиции.")


def new_document(session: Session, **fields) -> InventoryDocument:
    number = session.scalar(select(inventory_document_number_seq.next_value()))
    document = InventoryDocument(number=f"INV-{number:010d}", **fields)
    session.add(document)
    session.flush()
    return document


def save_line(
    session: Session,
    document: InventoryDocument,
    item_id: uuid.UUID,
    line_number: int,
    quantity: int,
    delta: int,
    snapshot: dict,
    reversal_of_id: uuid.UUID | None = None,
) -> None:
    line = InventoryDocumentItem(
        document_id=document.id,
        inventory_item_id=item_id,
        line_number=line_number,
        quantity=quantity,
        **snapshot,
    )
    session.add(line)
    session.flush()
    session.add(
        InventoryMovement(
            document_item_id=line.id,
            inventory_item_id=item_id,
            delta=delta,
            reversal_of_id=reversal_of_id,
        )
    )


def conduct(
    session: Session,
    actor: User,
    session_hash: str,
    key: uuid.UUID,
    payload: ReceiptInput | IssueInput,
    *,
    commit: bool = True,
) -> tuple[dict, bool]:
    issue = isinstance(payload, IssueInput)
    kind = "issue" if issue else "receipt"
    permission = "inventory.issue" if issue else "inventory.manage"
    fingerprint = request_hash(payload.model_dump(mode="json"))
    lock_command(session, actor.id, kind, key)
    previous = replay(session, actor, session_hash, kind, key, fingerprint, permission)
    if previous is not None:
        return previous, False
    recipient = {}
    if issue:
        employee, department = lock_recipient(session, payload.recipient_employee_id)
        recipient = {
            "recipient_employee_id": employee.id,
            "recipient_name": employee.full_name,
            "recipient_personnel_number": employee.personnel_number,
            "recipient_department": department.name,
            "recipient_room": payload.recipient_room,
        }
    items = lock_items(session, [line.inventory_item_id for line in payload.items])
    revalidate_mutation(session, actor, session_hash, permission)
    if any(item.archived_at for item in items.values()):
        fail(409, "item_archived", "Архивную позицию нельзя использовать в новом документе.")
    deltas = {
        line.inventory_item_id: line.quantity * (-1 if issue else 1) for line in payload.items
    }
    check_balances(session, deltas)
    document = new_document(
        session,
        document_type=kind,
        created_by_id=actor.id,
        document_date=payload.document_date,
        comment=payload.comment,
        idempotency_key=key,
        request_hash=fingerprint,
        receipt_purpose=None if issue else payload.receipt_purpose,
        external_number=None if issue else payload.external_number,
        supplier_name=None if issue else payload.supplier_name,
        **recipient,
    )
    for index, line in enumerate(payload.items, 1):
        item = items[line.inventory_item_id]
        manufacturer = session.scalar(
            select(Manufacturer.name).where(Manufacturer.id == item.manufacturer_id)
        )
        save_line(
            session,
            document,
            item.id,
            index,
            line.quantity,
            deltas[item.id],
            {
                "internal_code": item.internal_code,
                "model": item.model,
                "manufacturer": manufacturer,
                "unit": "pcs",
            },
        )
    audit(session, actor.id, f"inventory.{kind}", document.id)
    session.flush()
    result = document_response(session, document)
    if commit:
        session.commit()
    return result, True


def cancel(
    session: Session,
    actor: User,
    session_hash: str,
    key: uuid.UUID,
    document_id: uuid.UUID,
    payload: ReversalInput,
) -> tuple[dict, bool]:
    fingerprint = request_hash({**payload.model_dump(mode="json"), "document_id": str(document_id)})
    lock_command(session, actor.id, "reversal", key)
    previous = replay(
        session, actor, session_hash, "reversal", key, fingerprint, "inventory.manage"
    )
    if previous is not None:
        return previous, False
    original = get_document(session, document_id)
    if original.document_type == "reversal":
        fail(409, "reversal_not_allowed", "Отмена документа отмены не допускается.")
    lines = session.execute(
        select(InventoryDocumentItem, InventoryMovement)
        .join(InventoryMovement, InventoryMovement.document_item_id == InventoryDocumentItem.id)
        .where(InventoryDocumentItem.document_id == original.id)
        .order_by(InventoryDocumentItem.line_number)
    ).all()
    items = lock_items(session, [line.inventory_item_id for line, _ in lines])
    revalidate_mutation(session, actor, session_hash, "inventory.manage")
    if session.scalar(
        select(InventoryDocument.id).where(InventoryDocument.reversal_of_id == original.id)
    ):
        fail(409, "already_cancelled", "Документ уже отменён.")
    deltas = {line.inventory_item_id: -movement.delta for line, movement in lines}
    check_balances(session, deltas)
    document = new_document(
        session,
        document_type="reversal",
        created_by_id=actor.id,
        document_date=datetime.now(ZoneInfo("Asia/Yekaterinburg")).date(),
        reversal_of_id=original.id,
        reason=payload.reason,
        comment="",
        idempotency_key=key,
        request_hash=fingerprint,
        recipient_employee_id=original.recipient_employee_id,
        recipient_name=original.recipient_name,
        recipient_personnel_number=original.recipient_personnel_number,
        recipient_department=original.recipient_department,
        recipient_room=original.recipient_room,
        supplier_name=original.supplier_name,
    )
    for line, movement in lines:
        item = items[line.inventory_item_id]
        if item.archived_at and deltas[item.id] > 0:
            item.archived_at = None
            item.version += 1
            item.updated_at = datetime.now(UTC)
            audit(session, actor.id, "inventory.item_restored_by_reversal", item.id)
        save_line(
            session,
            document,
            item.id,
            line.line_number,
            line.quantity,
            -movement.delta,
            {
                name: getattr(line, name)
                for name in ("internal_code", "model", "manufacturer", "unit")
            },
            reversal_of_id=movement.id,
        )
    audit(session, actor.id, "inventory.reversal", document.id)
    session.flush()
    result = document_response(session, document)
    session.commit()
    return result, True
