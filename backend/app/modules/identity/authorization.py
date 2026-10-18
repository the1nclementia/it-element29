"""Serialize a mutation against account changes after waiting for resource locks."""

from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.identity.errors import fail
from app.modules.identity.models import AuthSession, User
from app.modules.identity.repository import permissions_for


def revalidate_mutation(session: Session, actor: User, session_hash: str, permission: str) -> User:
    # Shared readers do not serialize independent inventory operations. Identity changes
    # take the existing exclusive (29, 2) lock. Resource locks must precede this call.
    session.execute(text("SELECT pg_advisory_xact_lock_shared(29, 2)"))
    current = session.scalar(
        select(User)
        .where(User.id == actor.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    alive = session.scalar(
        select(AuthSession.token_hash)
        .where(
            AuthSession.token_hash == session_hash,
            AuthSession.user_id == actor.id,
            AuthSession.expires_at > datetime.now(UTC),
        )
        .with_for_update(read=True)
    )
    if not current or not current.is_active or alive is None:
        fail(401, "unauthenticated", "Сессия завершена. Войдите снова.")
    if current.must_change_password:
        fail(403, "password_change_required", "Перед продолжением смените временный пароль.")
    if permission not in permissions_for(session, current.role_code):
        fail(403, "forbidden", "Недостаточно прав для этого действия.")
    return current
