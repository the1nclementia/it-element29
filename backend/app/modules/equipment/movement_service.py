import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentInstance, EquipmentMovement
from app.modules.identity.authorization import revalidate_mutation
from app.modules.identity.errors import fail
from app.modules.identity.models import User
from app.modules.identity.repository import audit
from app.modules.inventory import stock_service
from app.modules.inventory.document_service import document_response
from app.modules.inventory.equipment_document_models import InventoryDocumentEquipment
from app.modules.inventory.models import InventoryItem, Manufacturer


def _source(instance: EquipmentInstance) -> dict:
    return {
        "current_building": instance.current_building,
        "current_room": instance.current_room,
        "current_department": instance.current_department,
        "current_recipient": instance.current_recipient,
    }


def _lock_instances(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, EquipmentInstance]:
    rows = session.scalars(
        select(EquipmentInstance)
        .where(EquipmentInstance.id.in_(ids))
        .order_by(EquipmentInstance.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    result = {row.id: row for row in rows}
    if len(result) != len(ids):
        fail(404, "instance_not_found", "Один из экземпляров не найден.")
    return result


def move(
    session: Session,
    actor: User,
    session_hash: str,
    key: uuid.UUID,
    payload,
) -> tuple[dict, bool]:
    fingerprint = stock_service.request_hash(payload.model_dump(mode="json"))
    stock_service.lock_command(session, actor.id, "transfer", key)
    previous = stock_service.replay(
        session, actor, session_hash, "transfer", key, fingerprint, "movements.manage"
    )
    if previous is not None:
        return previous, False
    rows = _lock_instances(session, [line.equipment_instance_id for line in payload.items])
    revalidate_mutation(session, actor, session_hash, "movements.manage")
    for line in payload.items:
        instance = rows[line.equipment_instance_id]
        if instance.archived_at:
            fail(409, "instance_archived", "Архивный экземпляр нельзя переместить.")
        if instance.is_under_repair:
            fail(409, "instance_under_repair", "Экземпляр находится на ремонте.")
        if instance.version != line.version:
            fail(409, "version_conflict", "Состояние экземпляра изменилось. Обновите список.")
        if _source(instance) != {
            "current_building": line.current_building,
            "current_room": line.current_room,
            "current_department": line.current_department,
            "current_recipient": line.current_recipient,
        }:
            fail(409, "placement_conflict", "Текущее положение экземпляра изменилось.")
        if not any(_source(instance).values()):
            fail(409, "instance_not_in_use", "Со склада можно выполнить выдачу, а не перемещение.")
    document = stock_service.new_document(
        session,
        document_type="transfer",
        created_by_id=actor.id,
        document_date=payload.document_date,
        comment=payload.comment,
        idempotency_key=key,
        request_hash=fingerprint,
        recipient_employee_id=None,
        recipient_name=payload.destination_recipient,
        recipient_department=payload.destination_department,
        recipient_building=payload.destination_building,
        recipient_room=payload.destination_room,
        recipient_personnel_number=None,
        receipt_purpose=None,
        external_number=None,
        supplier_name=None,
        reversal_of_id=None,
        reason=None,
    )
    destination = {
        "current_building": payload.destination_building,
        "current_room": payload.destination_room,
        "current_department": payload.destination_department,
        "current_recipient": payload.destination_recipient,
    }
    for line_number, line in enumerate(payload.items, 1):
        instance = rows[line.equipment_instance_id]
        before = _source(instance)
        item = session.get(InventoryItem, instance.inventory_item_id)
        if item is None:
            fail(409, "item_not_found", "Номенклатура экземпляра не найдена.")
        manufacturer = session.scalar(
            select(Manufacturer.name).where(Manufacturer.id == instance.manufacturer_id)
        )
        if manufacturer is None:
            fail(409, "manufacturer_not_found", "Производитель экземпляра не найден.")
        session.add(
            InventoryDocumentEquipment(
                document_id=document.id,
                equipment_instance_id=instance.id,
                line_number=line_number,
                internal_code=item.internal_code,
                model=item.model,
                manufacturer=manufacturer,
                serial_number=instance.serial_number,
                inventory_number=instance.inventory_number,
            )
        )
        session.add(
            EquipmentMovement(
                equipment_instance_id=instance.id,
                document_id=document.id,
                movement_type="transfer",
                before_building=before["current_building"],
                before_room=before["current_room"],
                before_department=before["current_department"],
                before_recipient=before["current_recipient"],
                after_building=destination["current_building"],
                after_room=destination["current_room"],
                after_department=destination["current_department"],
                after_recipient=destination["current_recipient"],
            )
        )
        for field, value in destination.items():
            setattr(instance, field, value)
        instance.version += 1
    audit(session, actor.id, "equipment.transfer", document.id)
    session.flush()
    result = document_response(session, document)
    session.commit()
    return result, True


def history(session: Session, instance_id: uuid.UUID | None, offset: int, limit: int) -> dict:
    query = (
        select(EquipmentMovement, EquipmentInstance, InventoryItem, Manufacturer)
        .join(EquipmentInstance, EquipmentInstance.id == EquipmentMovement.equipment_instance_id)
        .join(InventoryItem, InventoryItem.id == EquipmentInstance.inventory_item_id)
        .join(Manufacturer, Manufacturer.id == EquipmentInstance.manufacturer_id)
    )
    if instance_id:
        query = query.where(EquipmentMovement.equipment_instance_id == instance_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(
        query.order_by(EquipmentMovement.occurred_at.desc(), EquipmentMovement.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "total": total,
        "items": [
            {
                "id": row.id,
                "equipment_instance_id": row.equipment_instance_id,
                "internal_code": item.internal_code,
                "model": item.model,
                "manufacturer_name": manufacturer.name,
                "serial_number": instance.serial_number,
                "inventory_number": instance.inventory_number,
                "document_id": row.document_id,
                "movement_type": row.movement_type,
                "occurred_at": row.occurred_at,
                "before": {
                    "building": row.before_building,
                    "room": row.before_room,
                    "department": row.before_department,
                    "recipient": row.before_recipient,
                },
                "after": {
                    "building": row.after_building,
                    "room": row.after_room,
                    "department": row.after_department,
                    "recipient": row.after_recipient,
                },
            }
            for row, instance, item, manufacturer in rows
        ],
    }
