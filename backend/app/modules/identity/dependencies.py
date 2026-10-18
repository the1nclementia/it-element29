import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.identity.errors import fail
from app.modules.identity.models import AuthSession, User
from app.modules.identity.repository import permissions_for
from app.modules.identity.security import csrf_token, token_hash

Database = Annotated[Session, Depends(get_session)]
COOKIE_NAME = "element29_session"


def find_session(request: Request, session: Session) -> AuthSession | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 128:
        return None
    return session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash(token),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )


def check_csrf(request: Request, session: Database) -> AuthSession:
    if request.headers.get("origin") not in request.app.state.settings.app_origins:
        fail(403, "csrf_failed", "Источник запроса не разрешён. Обновите страницу.")
    token = request.cookies.get(COOKIE_NAME, "")
    supplied = request.headers.get("x-csrf-token", "")
    if (
        not token
        or len(token) > 128
        or not hmac.compare_digest(
            csrf_token(token).encode(),
            supplied.encode(),
        )
    ):
        fail(403, "csrf_failed", "Проверка безопасности не пройдена. Обновите страницу.")
    record = find_session(request, session)
    if record is None:
        fail(401, "session_expired", "Сессия истекла. Войдите снова.")
    return record


def current_user(request: Request, session: Database) -> User:
    record = find_session(request, session)
    user = session.get(User, record.user_id) if record and record.user_id else None
    if not user or not user.is_active:
        fail(401, "unauthenticated", "Войдите в систему.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
CsrfSession = Annotated[AuthSession, Depends(check_csrf)]


def require_permission(permission: str):
    def dependency(user: CurrentUser, session: Database) -> User:
        if user.must_change_password:
            fail(403, "password_change_required", "Перед продолжением смените временный пароль.")
        if permission not in permissions_for(session, user.role_code):
            fail(403, "forbidden", "Недостаточно прав для этого действия.")
        return user

    return dependency
