from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.modules.identity.dependencies import Database, require_permission
from app.modules.identity.models import AuditLog, User

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
}


@router.get("/dashboard")
def dashboard(
    user: Annotated[User, Depends(require_permission("dashboard.read"))], session: Database
):
    events = session.scalars(
        select(AuditLog)
        .where(AuditLog.actor_id == user.id)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id)
        .limit(5)
    )
    return {
        "metrics": [
            {"key": key, "label": label, "value": None, "available": False}
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
