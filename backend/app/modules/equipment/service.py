import uuid

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentInstance
from app.modules.identity.authorization import revalidate_mutation
from app.modules.identity.errors import fail
from app.modules.identity.repository import audit
from app.modules.inventory.models import InventoryItem, Manufacturer


def key(value: str | None) -> str | None:
    return " ".join(value.split()).casefold() if value else None


def response(session: Session, instance: EquipmentInstance) -> dict:
    item = session.get(InventoryItem, instance.inventory_item_id)
    manufacturer = session.get(Manufacturer, instance.manufacturer_id)
    return {
        "id": instance.id,
        "version": instance.version,
        "created_at": instance.created_at,
        "updated_at": instance.updated_at,
        "archived_at": instance.archived_at,
        "inventory_item_id": instance.inventory_item_id,
        "internal_code": item.internal_code,
        "model": item.model,
        "manufacturer_id": instance.manufacturer_id,
        "manufacturer_name": manufacturer.name,
        "serial_number": instance.serial_number,
        "inventory_number": instance.inventory_number,
        "current_building": instance.current_building,
        "current_room": instance.current_room,
        "current_department": instance.current_department,
        "current_recipient": instance.current_recipient,
        "is_under_repair": instance.is_under_repair,
    }


def list_instances(
    session: Session, *, q: str = "", inventory_item_id=None, archived="false", offset=0, limit=20
):
    query = select(EquipmentInstance)
    if archived == "false":
        query = query.where(EquipmentInstance.archived_at.is_(None))
    elif archived == "true":
        query = query.where(EquipmentInstance.archived_at.is_not(None))
    if inventory_item_id:
        query = query.where(EquipmentInstance.inventory_item_id == inventory_item_id)
    if q:
        pattern = f"%{q.replace('%', r'\\%').replace('_', r'\\_')}%"
        query = query.where(
            or_(
                EquipmentInstance.serial_number.ilike(pattern, escape="\\"),
                EquipmentInstance.inventory_number.ilike(pattern, escape="\\"),
                EquipmentInstance.current_recipient.ilike(pattern, escape="\\"),
            )
        )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(EquipmentInstance.created_at.desc(), EquipmentInstance.id)
        .offset(offset)
        .limit(limit)
    )
    return {"items": [response(session, row) for row in rows], "total": total}


def _lock_item(session: Session, item_id: uuid.UUID) -> InventoryItem:
    item = session.scalar(
        select(InventoryItem).where(InventoryItem.id == item_id).with_for_update(read=True)
    )
    if item is None:
        fail(404, "item_not_found", "Номенклатурная позиция не найдена.")
    if item.archived_at:
        fail(409, "item_archived", "Архивную позицию нельзя использовать.")
    if item.accounting_mode != "serialized":
        fail(409, "not_serialized_item", "Позиция не ведётся по экземплярам.")
    return item


def create(session: Session, actor, session_hash: str, payload) -> dict:
    item = _lock_item(session, payload.inventory_item_id)
    revalidate_mutation(session, actor, session_hash, "equipment.manage")
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": 2900000003})
    values = payload.model_dump()
    values["manufacturer_id"] = item.manufacturer_id
    values["serial_number_key"] = key(values["serial_number"])
    values["inventory_number_key"] = key(values["inventory_number"])
    instance = EquipmentInstance(**values)
    session.add(instance)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        fail(409, "duplicate_identifier", "Серийный или инвентарный номер уже зарегистрирован.")
    audit(
        session,
        actor.id,
        "equipment.instance_created",
        instance.id,
        {"fields": ["serial_number", "inventory_number"]},
    )
    session.commit()
    return response(session, instance)


def update(session: Session, actor, session_hash: str, instance_id: uuid.UUID, payload) -> dict:
    instance = session.scalar(
        select(EquipmentInstance).where(EquipmentInstance.id == instance_id).with_for_update()
    )
    if instance is None:
        fail(404, "instance_not_found", "Экземпляр не найден.")
    if instance.archived_at:
        fail(409, "instance_archived", "Экземпляр находится в архиве.")
    if instance.version != payload.version:
        fail(
            409, "version_conflict", "Экземпляр уже изменён. Обновите данные и повторите действие."
        )
    revalidate_mutation(session, actor, session_hash, "equipment.manage")
    values = payload.model_dump(exclude={"version"}, exclude_unset=True)
    for name in ("serial_number", "inventory_number"):
        if name in values:
            values[f"{name}_key"] = key(values[name])
    for name, value in values.items():
        setattr(instance, name, value)
    instance.version += 1
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        fail(409, "duplicate_identifier", "Серийный или инвентарный номер уже зарегистрирован.")
    audit(session, actor.id, "equipment.instance_updated", instance.id, {"fields": list(values)})
    session.commit()
    return response(session, instance)


def archive(
    session: Session,
    actor,
    session_hash: str,
    instance_id: uuid.UUID,
    version: int,
    archived: bool,
) -> dict:
    instance = session.scalar(
        select(EquipmentInstance).where(EquipmentInstance.id == instance_id).with_for_update()
    )
    if instance is None:
        fail(404, "instance_not_found", "Экземпляр не найден.")
    if archived and instance.archived_at:
        fail(409, "instance_archived", "Экземпляр уже находится в архиве.")
    if not archived and instance.archived_at is None:
        fail(409, "instance_active", "Экземпляр уже восстановлен.")
    if instance.version != version:
        fail(
            409, "version_conflict", "Экземпляр уже изменён. Обновите данные и повторите действие."
        )
    revalidate_mutation(session, actor, session_hash, "equipment.manage")
    instance.archived_at = func.now() if archived else None
    instance.version += 1
    audit(
        session,
        actor.id,
        "equipment.instance_archived" if archived else "equipment.instance_restored",
        instance.id,
    )
    session.commit()
    return response(session, instance)
