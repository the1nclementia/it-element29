import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.identity.errors import fail
from app.modules.identity.models import AuthSession, User
from app.modules.identity.repository import (
    audit,
    lock_administration,
    permissions_for,
    revoke_sessions,
)
from app.modules.identity.schemas import CreateUserInput, UpdateUserInput
from app.modules.identity.security import hash_password


def lock_admin(session: Session, actor: User, session_hash: str) -> User:
    lock_administration(session)
    actor = session.scalar(
        select(User)
        .where(User.id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # A request may have waited while a password change revoked its session.
    if (
        session.scalar(
            select(AuthSession.token_hash).where(
                AuthSession.token_hash == session_hash,
                AuthSession.user_id == actor.id,
                AuthSession.expires_at > datetime.now(UTC),
            )
        )
        is None
    ):
        fail(401, "unauthenticated", "Войдите в систему.")
    if (
        not actor.is_active
        or actor.must_change_password
        or "users.manage" not in permissions_for(session, actor.role_code)
    ):
        fail(403, "forbidden", "Недостаточно прав для этого действия.")
    return actor


def get_target(session: Session, target_id: uuid.UUID) -> User:
    user = session.scalar(
        select(User)
        .where(User.id == target_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        fail(404, "user_not_found", "Пользователь не найден.")
    return user


def create_user(session: Session, actor: User, payload: CreateUserInput, session_hash: str) -> User:
    actor = lock_admin(session, actor, session_hash)
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        role_code=payload.role,
        password_hash=hash_password(payload.password.get_secret_value()),
        is_active=True,
        must_change_password=True,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        fail(409, "username_exists", "Пользователь с таким логином уже существует.")
    audit(
        session,
        actor.id,
        "user.created",
        user.id,
        {"role": payload.role, "username": user.username},
    )
    session.commit()
    return user


def update_user(
    session: Session,
    actor: User,
    target_id: uuid.UUID,
    payload: UpdateUserInput,
    session_hash: str,
) -> User:
    actor = lock_admin(session, actor, session_hash)
    user = get_target(session, target_id)
    changes = payload.model_dump(exclude_unset=True)
    if user.id == actor.id and (
        changes.get("is_active") is False
        or ("role" in changes and changes["role"] != user.role_code)
    ):
        fail(409, "self_lockout", "Нельзя заблокировать себя или изменить собственную роль.")
    losing_admin = changes.get("is_active") is False or (
        "role" in changes and changes["role"] != "administrator"
    )
    if user.is_active and user.role_code == "administrator" and losing_admin:
        active_admins = session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.is_active.is_(True),
                User.role_code == "administrator",
            )
        )
        if active_admins <= 1:
            fail(409, "last_administrator", "Нельзя отключить последнего администратора.")
    audit_changes = {}
    for field, value in changes.items():
        attribute = "role_code" if field == "role" else field
        old = getattr(user, attribute)
        if old != value:
            audit_changes[field] = {"old": old, "new": value}
            setattr(user, attribute, value)
    if "role" in audit_changes or "is_active" in audit_changes:
        revoke_sessions(session, user.id)
    if audit_changes:
        audit(session, actor.id, "user.updated", user.id, audit_changes)
    session.commit()
    return user


def reset_password(
    session: Session, actor: User, target_id: uuid.UUID, password: str, session_hash: str
) -> None:
    actor = lock_admin(session, actor, session_hash)
    user = get_target(session, target_id)
    if user.id == actor.id:
        fail(409, "use_password_settings", "Свой пароль измените в настройках профиля.")
    user.password_hash = hash_password(password)
    user.must_change_password = True
    revoke_sessions(session, user.id)
    audit(session, actor.id, "user.password_reset", user.id)
    session.commit()
