import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.modules.identity.dependencies import CsrfSession, CurrentUser, Database
from app.modules.identity.models import User
from app.modules.inventory import draft_service as service
from app.modules.inventory.draft_schemas import DraftCreate, DraftUpdate, DraftVersion

router = APIRouter(prefix="/inventory/drafts", tags=["Личные складские черновики"])


def draft_user(actor: CurrentUser, session: Database):
    service.allowed_types(session, actor)
    return actor


DraftUser = Annotated[User, Depends(draft_user)]


@router.get("")
def drafts(
    session: Database,
    actor: DraftUser,
    document_type: Literal["receipt", "issue"] | None = None,
    status: Literal["draft", "posted", "archived", "all"] = "draft",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    return service.list_drafts(
        session, actor, document_type=document_type, status=status, offset=offset, limit=limit
    )


@router.post("", status_code=201)
def create(
    payload: DraftCreate, session: Database, actor: DraftUser, csrf: CsrfSession, response: Response
):
    result, created = service.create(session, actor, csrf.token_hash, payload)
    response.status_code = 201 if created else 200
    return result


@router.get("/{draft_id}")
def draft(draft_id: uuid.UUID, session: Database, actor: DraftUser):
    return service.response(service.own_draft(session, actor, draft_id))


@router.patch("/{draft_id}")
def update(
    draft_id: uuid.UUID,
    payload: DraftUpdate,
    session: Database,
    actor: DraftUser,
    csrf: CsrfSession,
):
    return service.update(session, actor, csrf.token_hash, draft_id, payload)


@router.post("/{draft_id}/archive")
def archive(
    draft_id: uuid.UUID,
    payload: DraftVersion,
    session: Database,
    actor: DraftUser,
    csrf: CsrfSession,
):
    return service.archive(session, actor, csrf.token_hash, draft_id, payload.version)


@router.post("/{draft_id}/post", status_code=201)
def post(
    draft_id: uuid.UUID,
    payload: DraftVersion,
    session: Database,
    actor: DraftUser,
    csrf: CsrfSession,
    response: Response,
):
    result, created = service.post(session, actor, csrf.token_hash, draft_id, payload.version)
    response.status_code = 201 if created else 200
    return result
