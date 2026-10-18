"""Каталог: версии, архивирование и совместимость под блокировками ресурсов."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.files.models import InventoryItemAttachment
from app.modules.identity.authorization import revalidate_mutation
from app.modules.identity.errors import fail
from app.modules.identity.repository import audit
from app.modules.inventory.models import (
    InventoryCategory,
    InventoryCompatibility,
    InventoryItem,
    Manufacturer,
    PrinterModel,
)
from app.modules.inventory.repository import (
    archived_filter,
    balance_query,
    escaped_like,
    get_balance,
)


def normalize_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def locked(session: Session, model, record_id: uuid.UUID, *, active=False, shared=False):
    record = session.scalar(
        select(model)
        .where(model.id == record_id)
        .with_for_update(read=shared)
        .execution_options(populate_existing=True)
    )
    if record is None:
        fail(404, "not_found", "Запись не найдена.")
    if active and record.archived_at is not None:
        fail(409, "reference_archived", "Связанная запись находится в архиве.")
    return record


def check_version(record, version: int):
    if record.version != version:
        fail(409, "version_conflict", "Запись уже изменена. Обновите данные и повторите действие.")


def commit(session: Session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        fail(409, "duplicate_record", "Запись с такими уникальными полями уже существует.")


def base_response(record):
    return {
        name: getattr(record, name)
        for name in ("id", "version", "created_at", "updated_at", "archived_at")
    }


def reference_response(session: Session, record):
    result = base_response(record)
    if isinstance(record, Manufacturer):
        result["name"] = record.name
    elif isinstance(record, InventoryCategory):
        result.update(code=record.code, name=record.name)
    else:
        result.update(
            manufacturer_id=record.manufacturer_id,
            model=record.model,
            manufacturer_name=session.get(Manufacturer, record.manufacturer_id).name,
        )
    return result


def item_response(session: Session, item: InventoryItem, balance: int | None = None):
    if balance is None:
        balance = get_balance(session, item.id)
    photo_id = session.scalar(
        select(InventoryItemAttachment.file_attachment_id).where(
            InventoryItemAttachment.inventory_item_id == item.id,
            InventoryItemAttachment.archived_at.is_(None),
            InventoryItemAttachment.is_primary.is_(True),
        )
    )
    return {
        **base_response(item),
        **{
            name: getattr(item, name)
            for name in (
                "internal_code",
                "category_id",
                "manufacturer_id",
                "model",
                "article",
                "description",
                "min_stock",
            )
        },
        "category_name": session.get(InventoryCategory, item.category_id).name,
        "manufacturer_name": session.get(Manufacturer, item.manufacturer_id).name,
        "balance": balance,
        "unit": "pcs",
        "is_low_stock": item.min_stock > 0 and balance < item.min_stock,
        "primary_photo_url": f"/api/v1/inventory/items/{item.id}/photos/{photo_id}/content"
        if photo_id
        else None,
    }


def list_references(
    session: Session, model, *, q="", archived="false", offset=0, limit=20, manufacturer_id=None
):
    statement = archived_filter(select(model), model, archived)
    fields = [model.model] if model is PrinterModel else [model.name]
    if model is InventoryCategory:
        fields.append(model.code)
    if q:
        statement = statement.where(
            or_(*(field.ilike(escaped_like(q), escape="\\") for field in fields))
        )
    if manufacturer_id and model is PrinterModel:
        statement = statement.where(model.manufacturer_id == manufacturer_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    sort = model.model if model is PrinterModel else model.name
    records = session.scalars(statement.order_by(sort, model.id).offset(offset).limit(limit))
    return {"items": [reference_response(session, record) for record in records], "total": total}


def save_reference(session: Session, actor, session_hash, model, payload, record_id=None):
    values = payload.model_dump(exclude_unset=True)
    version = values.pop("version", None)
    if model is PrinterModel:
        previous = session.get(model, record_id) if record_id else None
        if record_id and previous is None:
            fail(404, "not_found", "Модель принтера не найдена.")
        previous_manufacturer = previous.manufacturer_id if previous else None
        target_manufacturer = values.get("manufacturer_id", previous_manufacturer)
        for manufacturer_id in sorted(
            {target_manufacturer, previous_manufacturer} - {None}, key=str
        ):
            locked(
                session,
                Manufacturer,
                manufacturer_id,
                active=not previous or target_manufacturer != previous_manufacturer,
                shared=True,
            )
    record = locked(session, model, record_id) if record_id else None
    if model is PrinterModel and record and record.manufacturer_id != previous_manufacturer:
        fail(409, "operation_busy", "Связи изменились. Обновите данные и повторите действие.")
    if record:
        check_version(record, version)
        if record.archived_at is not None:
            fail(409, "record_archived", "Сначала восстановите запись из архива.")
    revalidate_mutation(session, actor, session_hash, "inventory.manage")
    if model is Manufacturer and "name" in values:
        values["name_key"] = normalize_key(values["name"])
    if model is PrinterModel and "model" in values:
        values["model_key"] = normalize_key(values["model"])
    if record is None:
        record = model(**values)
        session.add(record)
    else:
        for name, value in values.items():
            setattr(record, name, value)
        record.version += 1
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        fail(409, "duplicate_record", "Такая запись уже существует.")
    audit(
        session,
        actor.id,
        "inventory.reference_updated" if record_id else "inventory.reference_created",
        record.id,
        {"fields": sorted(set(values) - {"name_key", "model_key"})},
    )
    commit(session)
    return reference_response(session, record)


def archive_reference(session: Session, actor, session_hash, model, record_id, version, archived):
    record = locked(session, model, record_id)
    check_version(record, version)
    revalidate_mutation(session, actor, session_hash, "inventory.manage")
    record.archived_at = datetime.now(UTC) if archived else None
    record.version += 1
    audit(
        session,
        actor.id,
        "inventory.reference_archived" if archived else "inventory.reference_restored",
        record.id,
    )
    commit(session)
    return reference_response(session, record)


def list_items(
    session: Session,
    *,
    q="",
    category_id=None,
    manufacturer_id=None,
    printer_model_id=None,
    in_stock=None,
    low_stock=None,
    archived="false",
    sort="code",
    direction="asc",
    offset=0,
    limit=20,
):
    ledger = balance_query()
    amount = func.coalesce(ledger.c.balance, 0)
    statement = archived_filter(
        select(InventoryItem, amount).outerjoin(ledger, ledger.c.item_id == InventoryItem.id),
        InventoryItem,
        archived,
    )
    if q:
        statement = statement.where(
            or_(
                *(
                    field.ilike(escaped_like(q), escape="\\")
                    for field in (
                        InventoryItem.internal_code,
                        InventoryItem.model,
                        InventoryItem.article,
                    )
                )
            )
        )
    if category_id:
        statement = statement.where(InventoryItem.category_id == category_id)
    if manufacturer_id:
        statement = statement.where(InventoryItem.manufacturer_id == manufacturer_id)
    if printer_model_id:
        statement = statement.where(
            select(InventoryCompatibility.id)
            .where(
                InventoryCompatibility.inventory_item_id == InventoryItem.id,
                InventoryCompatibility.printer_model_id == printer_model_id,
                InventoryCompatibility.archived_at.is_(None),
            )
            .exists()
        )
    if in_stock is not None:
        statement = statement.where((amount > 0) if in_stock else (amount == 0))
    if low_stock is not None:
        low = (InventoryItem.min_stock > 0) & (amount < InventoryItem.min_stock)
        statement = statement.where(low if low_stock else ~low)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    order = {"code": InventoryItem.internal_code, "model": InventoryItem.model, "balance": amount}[
        sort
    ]
    rows = session.execute(
        statement.order_by(order.desc() if direction == "desc" else order.asc(), InventoryItem.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [item_response(session, item, int(amount)) for item, amount in rows],
        "total": total,
    }


def get_item(session: Session, item_id):
    item = session.get(InventoryItem, item_id)
    if item is None:
        fail(404, "not_found", "Складская позиция не найдена.")
    return item


def save_item(session: Session, actor, session_hash, payload, item_id=None):
    values = payload.model_dump(exclude_unset=True)
    version = values.pop("version", None)
    previous = get_item(session, item_id) if item_id else None
    old_refs = {
        field: getattr(previous, field) if previous else None
        for field in ("manufacturer_id", "category_id")
    }
    for model, field in ((Manufacturer, "manufacturer_id"), (InventoryCategory, "category_id")):
        target = values.get(field, old_refs[field])
        for reference_id in sorted({target, old_refs[field]} - {None}, key=str):
            locked(
                session,
                model,
                reference_id,
                active=not previous or target != old_refs[field],
                shared=True,
            )
    item = locked(session, InventoryItem, item_id) if item_id else None
    if item:
        if any(getattr(item, field) != value for field, value in old_refs.items()):
            fail(409, "operation_busy", "Связи изменились. Обновите данные и повторите действие.")
        check_version(item, version)
        if item.archived_at is not None:
            fail(409, "record_archived", "Сначала восстановите позицию из архива.")
    revalidate_mutation(session, actor, session_hash, "inventory.manage")
    if item is None:
        item = InventoryItem(**values)
        session.add(item)
    else:
        for name, value in values.items():
            setattr(item, name, value)
        item.version += 1
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        fail(409, "duplicate_record", "Позиция с таким кодом уже существует.")
    audit(
        session,
        actor.id,
        "inventory.item_updated" if item_id else "inventory.item_created",
        item.id,
        {"fields": sorted(values)},
    )
    commit(session)
    return item_response(session, item)


def archive_item(session: Session, actor, session_hash, item_id, version, archived):
    item = locked(session, InventoryItem, item_id)
    check_version(item, version)
    revalidate_mutation(session, actor, session_hash, "inventory.manage")
    if archived and get_balance(session, item.id) != 0:
        fail(409, "nonzero_stock", "Можно архивировать только позицию с нулевым остатком.")
    item.archived_at = datetime.now(UTC) if archived else None
    item.version += 1
    audit(
        session,
        actor.id,
        "inventory.item_archived" if archived else "inventory.item_restored",
        item.id,
    )
    commit(session)
    return item_response(session, item)


def list_compatibilities(session: Session, item_id):
    get_item(session, item_id)
    models = list(
        session.scalars(
            select(PrinterModel)
            .join(
                InventoryCompatibility, InventoryCompatibility.printer_model_id == PrinterModel.id
            )
            .where(
                InventoryCompatibility.inventory_item_id == item_id,
                InventoryCompatibility.archived_at.is_(None),
            )
            .order_by(PrinterModel.model, PrinterModel.id)
        )
    )
    return {"items": [reference_response(session, model) for model in models], "total": len(models)}


def set_compatibilities(session: Session, actor, session_hash, item_id, payload):
    for model_id in sorted(payload.printer_model_ids, key=str):
        locked(session, PrinterModel, model_id, active=True, shared=True)
    item = locked(session, InventoryItem, item_id, active=True)
    check_version(item, payload.version)
    revalidate_mutation(session, actor, session_hash, "inventory.manage")
    links = {
        link.printer_model_id: link
        for link in session.scalars(
            select(InventoryCompatibility).where(
                InventoryCompatibility.inventory_item_id == item_id
            )
        )
    }
    desired = set(payload.printer_model_ids)
    for model_id, link in links.items():
        link.archived_at = None if model_id in desired else datetime.now(UTC)
    for model_id in desired - links.keys():
        session.add(InventoryCompatibility(inventory_item_id=item_id, printer_model_id=model_id))
    item.version += 1
    audit(
        session,
        actor.id,
        "inventory.compatibilities_updated",
        item.id,
        {"printer_model_ids": [str(value) for value in sorted(desired, key=str)]},
    )
    commit(session)
    return item_response(session, item)
