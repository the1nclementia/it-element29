import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.modules.identity.models import AuditLog, AuthSession, RolePermission, User
from app.modules.identity.permissions import ROLE_NAMES
from app.modules.identity.schemas import UserResponse


def permissions_for(session: Session, role_code: str) -> list[str]:
    return list(
        session.scalars(
            select(RolePermission.permission_code)
            .where(
                RolePermission.role_code == role_code,
            )
            .order_by(RolePermission.permission_code)
        )
    )


def user_response(session: Session, user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role_code,
        role_name=ROLE_NAMES[user.role_code],
        permissions=permissions_for(session, user.role_code),
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
    )


def revoke_sessions(session: Session, user_id: uuid.UUID) -> None:
    session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


def audit(
    session: Session,
    actor_id: uuid.UUID | None,
    action: str,
    target_id: uuid.UUID | None = None,
    changes: dict | None = None,
) -> None:
    # Only these non-secret fields may enter an audit record, including nested values.
    allowed = {"display_name", "role", "is_active", "username", "must_change_password"}
    safe = {key: value for key, value in (changes or {}).items() if key in allowed}
    if action.startswith("inventory.") and changes:
        # Record field names, never free-text catalogue values or uploaded content.
        catalog_fields = {
            "name",
            "code",
            "manufacturer_id",
            "model",
            "category_id",
            "internal_code",
            "article",
            "description",
            "min_stock",
            "accounting_mode",
            "item_type",
        }
        fields = changes.get("fields")
        if isinstance(fields, list):
            safe["fields"] = [
                field for field in fields if isinstance(field, str) and field in catalog_fields
            ]
        model_ids = changes.get("printer_model_ids")
        if isinstance(model_ids, list):
            safe["printer_model_ids"] = []
            for value in model_ids:
                if isinstance(value, str):
                    try:
                        safe["printer_model_ids"].append(str(uuid.UUID(value)))
                    except ValueError:
                        continue
    if action.startswith("equipment.") and changes:
        fields = changes.get("fields")
        if isinstance(fields, list):
            safe["fields"] = [
                field
                for field in fields
                if isinstance(field, str)
                and field
                in {
                    "serial_number",
                    "inventory_number",
                    "current_building",
                    "current_room",
                    "current_department",
                    "current_recipient",
                    "is_under_repair",
                }
            ]
    session.add(AuditLog(actor_id=actor_id, action=action, target_id=target_id, changes=safe))


def lock_administration(session: Session) -> None:
    session.execute(text("SELECT pg_advisory_xact_lock(29, 2)"))
