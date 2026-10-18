import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.identity.dependencies import COOKIE_NAME, find_session
from app.modules.identity.errors import fail
from app.modules.identity.models import AuthRateLimit, AuthSession, User
from app.modules.identity.repository import (
    audit,
    lock_administration,
    revoke_sessions,
    user_response,
)
from app.modules.identity.schemas import ChangePasswordInput, CreateUserInput, LoginInput
from app.modules.identity.security import (
    csrf_token,
    hash_password,
    password_hasher,
    token_hash,
    verify_password,
)


def new_session(
    session: Session, response: Response, settings: Settings, user_id: uuid.UUID | None
) -> str:
    raw = secrets.token_urlsafe(32)
    duration = timedelta(hours=settings.session_hours) if user_id else timedelta(minutes=15)
    session.add(
        AuthSession(
            token_hash=token_hash(raw), user_id=user_id, expires_at=datetime.now(UTC) + duration
        )
    )
    response.set_cookie(
        COOKIE_NAME,
        raw,
        max_age=int(duration.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return csrf_token(raw)


def get_csrf(request: Request, response: Response, session: Session) -> dict:
    if find_session(request, session):
        return {"csrf_token": csrf_token(request.cookies[COOKIE_NAME])}
    session.execute(delete(AuthSession).where(AuthSession.expires_at <= datetime.now(UTC)))
    session.execute(
        delete(AuthRateLimit).where(
            AuthRateLimit.window_start < datetime.now(UTC) - timedelta(days=1),
        )
    )
    token = new_session(session, response, request.app.state.settings, None)
    session.commit()
    return {"csrf_token": token}


def consume_login_attempt(session: Session, settings: Settings, username: str, address: str) -> str:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.login_window_seconds)
    account_key = token_hash("account:" + username)
    keys = [
        (account_key, settings.login_limit),
        (token_hash("ip:" + address), settings.login_ip_limit),
    ]
    retry_after = 0
    # Stable ordering prevents bucket deadlocks across workers.
    for key, limit in sorted(keys):
        expired = AuthRateLimit.window_start <= cutoff
        statement = insert(AuthRateLimit).values(key_hash=key, attempts=1, window_start=now)
        statement = statement.on_conflict_do_update(
            index_elements=[AuthRateLimit.key_hash],
            set_={
                "attempts": case((expired, 1), else_=AuthRateLimit.attempts + 1),
                "window_start": case((expired, now), else_=AuthRateLimit.window_start),
            },
        ).returning(AuthRateLimit.attempts, AuthRateLimit.window_start)
        attempts, started = session.execute(statement).one()
        if attempts > limit:
            retry_after = max(
                retry_after,
                int(
                    (
                        started + timedelta(seconds=settings.login_window_seconds) - now
                    ).total_seconds()
                )
                + 1,
            )
    session.commit()  # Failed logins must not roll back the throttle counters.
    if retry_after:
        fail(
            429,
            "rate_limited",
            "Слишком много попыток входа. Повторите позже.",
            {"Retry-After": str(retry_after)},
        )
    return account_key


def authenticate(
    request: Request,
    response: Response,
    session: Session,
    pre_session: AuthSession,
    payload: LoginInput,
) -> dict:
    username = payload.username.strip().lower()
    address = request.client.host if request.client else "unknown"
    key = consume_login_attempt(session, request.app.state.settings, username, address)
    user = session.scalar(select(User).where(User.username == username).with_for_update())
    password = payload.password.get_secret_value()
    verified = verify_password(password, user.password_hash if user else None)
    if not user or not verified or not user.is_active:
        fail(401, "invalid_credentials", "Неверный логин или пароль.")
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    session.execute(delete(AuthRateLimit).where(AuthRateLimit.key_hash == key))
    session.execute(delete(AuthSession).where(AuthSession.token_hash == pre_session.token_hash))
    csrf = new_session(session, response, request.app.state.settings, user.id)
    audit(session, user.id, "auth.login", user.id)
    session.commit()
    return {"user": user_response(session, user), "csrf_token": csrf}


def change_password(
    request: Request,
    response: Response,
    session: Session,
    user: User,
    auth_session: AuthSession,
    payload: ChangePasswordInput,
) -> dict:
    lock_administration(session)
    user = session.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not user.is_active
        or session.get(AuthSession, auth_session.token_hash, populate_existing=True) is None
    ):
        fail(401, "unauthenticated", "Войдите в систему.")
    if not verify_password(payload.current_password.get_secret_value(), user.password_hash):
        fail(400, "wrong_current_password", "Текущий пароль указан неверно.")
    if payload.current_password.get_secret_value() == payload.new_password.get_secret_value():
        fail(400, "password_unchanged", "Новый пароль должен отличаться от текущего.")
    user.password_hash = hash_password(payload.new_password.get_secret_value())
    user.must_change_password = False
    revoke_sessions(session, user.id)
    csrf = new_session(session, response, request.app.state.settings, user.id)
    audit(session, user.id, "auth.password_changed", user.id)
    session.commit()
    return {"user": user_response(session, user), "csrf_token": csrf}


def bootstrap_admin(session: Session, username: str, display_name: str, password: str):
    payload = CreateUserInput(
        username=username, display_name=display_name, role="administrator", password=password
    )
    lock_administration(session)
    if session.scalar(select(func.count()).select_from(User)):
        raise ValueError("Первоначальная настройка уже выполнена: пользователи существуют.")
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        role_code="administrator",
        password_hash=hash_password(password),
        is_active=True,
        must_change_password=False,
    )
    session.add(user)
    session.flush()
    audit(session, user.id, "user.bootstrap", user.id)
    session.commit()
    return user_response(session, user)
