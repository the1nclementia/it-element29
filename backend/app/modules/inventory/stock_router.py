import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response

from app.modules.identity.dependencies import CsrfSession, Database, require_permission
from app.modules.identity.models import User
from app.modules.inventory import document_service, stock_service
from app.modules.inventory.stock_schemas import IssueInput, ReceiptInput, ReversalInput

router = APIRouter(prefix="/inventory", tags=["Складские документы"])
Reader = Annotated[User, Depends(require_permission("inventory.read"))]
Manager = Annotated[User, Depends(require_permission("inventory.manage"))]
Issuer = Annotated[User, Depends(require_permission("inventory.issue"))]
Key = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.post("/receipts", status_code=201)
def receipt(
    payload: ReceiptInput,
    user: Manager,
    session: Database,
    csrf: CsrfSession,
    key: Key,
    response: Response,
):
    result, created = stock_service.conduct(session, user, csrf.token_hash, key, payload)
    response.status_code = 201 if created else 200
    return result


@router.post("/issues", status_code=201)
def issue(
    payload: IssueInput,
    user: Issuer,
    session: Database,
    csrf: CsrfSession,
    key: Key,
    response: Response,
):
    result, created = stock_service.conduct(session, user, csrf.token_hash, key, payload)
    response.status_code = 201 if created else 200
    return result


@router.post("/documents/{document_id}/cancel", status_code=201)
def cancel(
    document_id: uuid.UUID,
    payload: ReversalInput,
    user: Manager,
    session: Database,
    csrf: CsrfSession,
    key: Key,
    response: Response,
):
    result, created = stock_service.cancel(
        session, user, csrf.token_hash, key, document_id, payload
    )
    response.status_code = 201 if created else 200
    return result


@router.get("/documents")
def documents(
    user: Reader,
    session: Database,
    offset: Offset = 0,
    limit: Limit = 20,
    document_type: Literal["receipt", "issue", "reversal"] | None = None,
    recipient_employee_id: uuid.UUID | None = None,
    created_by_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cancelled: bool | None = None,
):
    return document_service.list_documents(
        session,
        document_type=document_type,
        recipient_employee_id=recipient_employee_id,
        created_by_id=created_by_id,
        date_from=date_from,
        date_to=date_to,
        cancelled=cancelled,
        offset=offset,
        limit=limit,
    )


@router.get("/documents/{document_id}")
def document(document_id: uuid.UUID, user: Reader, session: Database):
    return document_service.document_response(
        session, document_service.get_document(session, document_id)
    )


@router.get("/items/{item_id}/movements")
def movements(
    item_id: uuid.UUID, user: Reader, session: Database, offset: Offset = 0, limit: Limit = 20
):
    return document_service.list_movements(session, item_id, offset, limit)
