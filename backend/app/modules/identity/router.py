import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select

from app.modules.identity import service, users
from app.modules.identity.dependencies import (
    COOKIE_NAME,
    CsrfSession,
    CurrentUser,
    Database,
    require_permission,
)
from app.modules.identity.models import Role, User
from app.modules.identity.repository import audit, permissions_for, user_response
from app.modules.identity.schemas import (
    ChangePasswordInput,
    CreateUserInput,
    LoginInput,
    ResetPasswordInput,
    UpdateUserInput,
    UserResponse,
)

router = APIRouter(tags=["Авторизация и пользователи"])
Admin = Annotated[User, Depends(require_permission("users.manage"))]


@router.get("/auth/csrf")
def csrf(request: Request, response: Response, session: Database):
    return service.get_csrf(request, response, session)


@router.post("/auth/login")
def login(
    request: Request,
    response: Response,
    session: Database,
    csrf_session: CsrfSession,
    payload: LoginInput,
):
    return service.authenticate(request, response, session, csrf_session, payload)


@router.get("/auth/me", response_model=UserResponse)
def me(user: CurrentUser, session: Database):
    return user_response(session, user)


@router.get("/auth/permissions")
def permissions(user: CurrentUser, session: Database):
    return {"permissions": permissions_for(session, user.role_code)}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, session: Database, csrf_session: CsrfSession):
    if csrf_session.user_id:
        audit(session, csrf_session.user_id, "auth.logout", csrf_session.user_id)
    session.delete(csrf_session)
    session.commit()
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
    )


@router.post("/auth/password")
def password(
    request: Request,
    response: Response,
    session: Database,
    user: CurrentUser,
    csrf_session: CsrfSession,
    payload: ChangePasswordInput,
):
    return service.change_password(request, response, session, user, csrf_session, payload)


@router.get("/roles")
def roles(admin: Admin, session: Database):
    return {
        "items": [
            {
                "code": role.code,
                "name": role.name,
                "permissions": permissions_for(session, role.code),
            }
            for role in session.scalars(select(Role).order_by(Role.name))
        ]
    }


@router.get("/users")
def list_users(
    admin: Admin,
    session: Database,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str = Query(default="", max_length=100),
):
    conditions = []
    if q.strip():
        conditions.append(
            or_(
                User.username.contains(q.strip().lower(), autoescape=True),
                User.display_name.icontains(q.strip(), autoescape=True),
            )
        )
    total = session.scalar(select(func.count()).select_from(User).where(*conditions))
    items = session.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc(), User.id)
        .offset(offset)
        .limit(limit)
    )
    return {"items": [user_response(session, user) for user in items], "total": total}


@router.post("/users", status_code=201, response_model=UserResponse)
def create_user(
    admin: Admin, session: Database, csrf_session: CsrfSession, payload: CreateUserInput
):
    return user_response(
        session, users.create_user(session, admin, payload, csrf_session.token_hash)
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    admin: Admin,
    session: Database,
    csrf_session: CsrfSession,
    payload: UpdateUserInput,
):
    return user_response(
        session, users.update_user(session, admin, user_id, payload, csrf_session.token_hash)
    )


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: uuid.UUID,
    admin: Admin,
    session: Database,
    csrf_session: CsrfSession,
    payload: ResetPasswordInput,
):
    users.reset_password(
        session, admin, user_id, payload.new_password.get_secret_value(), csrf_session.token_hash
    )
