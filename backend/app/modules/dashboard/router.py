from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.modules.equipment.models import EquipmentInstance
from app.modules.identity.dependencies import Database, require_permission
from app.modules.identity.models import AuditLog, User
from app.modules.inventory.models import (
    InventoryCategory,
    InventoryDocument,
    InventoryItem,
    InventoryMovement,
)
from app.modules.inventory.repository import low_stock_expression

router = APIRouter(tags=["Главная"])
METRICS = [
    ("equipment_total", "Всего оборудования"),
    ("equipment_active", "В эксплуатации"),
    ("equipment_stock", "На складе"),
    ("equipment_maintenance", "На обслуживании"),
    ("cartridge_balance", "Остаток картриджей"),
    ("issues_today", "Выдачи за сегодня"),
    ("movements_month", "Перемещения за месяц"),
    ("low_stock", "Низкие остатки"),
]
EVENT_NAMES = {
    "auth.login": "Вход в систему",
    "auth.logout": "Выход из системы",
    "auth.password_changed": "Изменён пароль профиля",
    "user.created": "Создан пользователь",
    "user.updated": "Обновлена учётная запись",
    "user.password_reset": "Сброшен пароль пользователя",
    "user.bootstrap": "Создан первый администратор",
    "inventory.receipt": "Проведено поступление на склад",
    "inventory.issue": "Проведена выдача со склада",
    "inventory.reversal": "Отменён складской документ",
    "inventory.item_restored_by_reversal": "Позиция восстановлена после отмены выдачи",
}


@router.get("/dashboard")
def dashboard(
    user: Annotated[User, Depends(require_permission("dashboard.read"))], session: Database
):
    balance = (
        select(
            InventoryMovement.inventory_item_id,
            func.sum(InventoryMovement.delta).label("quantity"),
        )
        .group_by(InventoryMovement.inventory_item_id)
        .subquery()
    )
    quantity = func.coalesce(balance.c.quantity, 0)
    active = (
        select(InventoryItem)
        .outerjoin(
            balance,
            balance.c.inventory_item_id == InventoryItem.id,
        )
        .where(InventoryItem.archived_at.is_(None))
    )
    cartridge_balance = session.scalar(
        active.with_only_columns(func.coalesce(func.sum(quantity), 0))
        .join(InventoryCategory, InventoryCategory.id == InventoryItem.category_id)
        .where(
            InventoryCategory.code == "cartridges",
            InventoryItem.accounting_mode == "quantity",
        )
    )
    low_stock = session.scalar(
        active.with_only_columns(func.count(InventoryItem.id)).where(
            low_stock_expression(quantity, InventoryItem.min_stock),
            InventoryItem.accounting_mode == "quantity",
        )
    )
    equipment_total = session.scalar(
        select(func.count())
        .select_from(EquipmentInstance)
        .where(EquipmentInstance.archived_at.is_(None))
    )
    equipment_maintenance = session.scalar(
        select(func.count())
        .select_from(EquipmentInstance)
        .where(EquipmentInstance.archived_at.is_(None), EquipmentInstance.is_under_repair.is_(True))
    )
    equipment_active = session.scalar(
        select(func.count())
        .select_from(EquipmentInstance)
        .where(
            EquipmentInstance.archived_at.is_(None),
            EquipmentInstance.is_under_repair.is_(False),
            EquipmentInstance.current_recipient.is_not(None),
        )
    )
    equipment_stock = session.scalar(
        select(func.count())
        .select_from(EquipmentInstance)
        .where(
            EquipmentInstance.archived_at.is_(None),
            EquipmentInstance.is_under_repair.is_(False),
            EquipmentInstance.current_recipient.is_(None),
        )
    )
    zone = ZoneInfo("Asia/Yekaterinburg")
    today = datetime.now(zone).date()
    start = datetime.combine(today, time.min, zone).astimezone(UTC)
    end = datetime.combine(today + timedelta(days=1), time.min, zone).astimezone(UTC)
    reversal = aliased(InventoryDocument)
    cancelled = (
        select(reversal.id)
        .where(
            reversal.reversal_of_id == InventoryDocument.id,
        )
        .exists()
    )
    issues_today = session.scalar(
        select(func.count())
        .select_from(InventoryDocument)
        .where(
            InventoryDocument.document_type == "issue",
            InventoryDocument.created_at >= start,
            InventoryDocument.created_at < end,
            ~cancelled,
        )
    )
    values = {
        "equipment_total": int(equipment_total),
        "equipment_active": int(equipment_active),
        "equipment_stock": int(equipment_stock),
        "equipment_maintenance": int(equipment_maintenance),
        "cartridge_balance": int(cartridge_balance),
        "low_stock": low_stock,
        "issues_today": issues_today,
    }
    events = session.scalars(
        select(AuditLog)
        .where(AuditLog.actor_id == user.id)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id)
        .limit(5)
    )
    return {
        "metrics": [
            {"key": key, "label": label, "value": values.get(key), "available": key in values}
            for key, label in METRICS
        ],
        "recent_events": [
            {
                "id": row.id,
                "title": EVENT_NAMES.get(row.action, "Обновление профиля"),
                "occurred_at": row.occurred_at,
            }
            for row in events
        ],
    }
