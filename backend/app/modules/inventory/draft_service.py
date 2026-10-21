"""Черновик, проведение и аудит завершаются одной транзакцией."""

import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.identity.authorization import revalidate_mutation
from app.modules.identity.errors import fail
from app.modules.identity.models import User
from app.modules.identity.repository import audit, permissions_for
from app.modules.inventory import stock_service
from app.modules.inventory.document_service import document_response, get_document
from app.modules.inventory.draft_models import InventoryDraft
from app.modules.inventory.draft_schemas import (
    DraftCreate,
    DraftUpdate,
    IssueDraftPayload,
    ReceiptDraftPayload,
)
from app.modules.inventory.stock_schemas import IssueInput, ReceiptInput

DRAFT_PERMISSIONS = {"receipt": "inventory.manage", "issue": "inventory.issue"}


def allowed_types(session: Session, actor: User) -> list[str]:
    if actor.must_change_password:
        fail(403, "password_change_required", "Перед продолжением смените временный пароль.")
    permissions = permissions_for(session, actor.role_code)
    result = [kind for kind, permission in DRAFT_PERMISSIONS.items() if permission in permissions]
    if not result:
        fail(403, "forbidden", "Недостаточно прав для работы с черновиками.")
    return result


def ensure_kind_permission(session: Session, actor: User, kind: str):
    if kind not in allowed_types(session, actor):
        fail(403, "forbidden", "Недостаточно прав для этого типа черновика.")


def normalize_payload(kind: str, payload: dict) -> dict:
    schema = ReceiptDraftPayload if kind == "receipt" else IssueDraftPayload
    try:
        return schema.model_validate(payload).model_dump(mode="json")
    except ValidationError:
        fail(422, "validation_error", "Проверьте поля и строки черновика.")


def response(draft: InventoryDraft) -> dict:
    return {
        name: getattr(draft, name)
        for name in (
            "id",
            "owner_id",
            "document_type",
            "payload",
            "version",
            "status",
            "posted_document_id",
            "created_at",
            "updated_at",
            "archived_at",
        )
    }


def own_draft(session: Session, actor: User, draft_id: uuid.UUID, *, lock=False):
    query = select(InventoryDraft).where(
        InventoryDraft.id == draft_id, InventoryDraft.owner_id == actor.id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    draft = session.scalar(query)
    if draft is None:
        fail(404, "draft_not_found", "Черновик не найден.")
    ensure_kind_permission(session, actor, draft.document_type)
    return draft


def list_drafts(
    session: Session, actor: User, *, document_type=None, status="draft", offset=0, limit=20
):
    types = allowed_types(session, actor)
    if document_type:
        ensure_kind_permission(session, actor, document_type)
        types = [document_type]
    query = select(InventoryDraft).where(
        InventoryDraft.owner_id == actor.id, InventoryDraft.document_type.in_(types)
    )
    if status != "all":
        query = query.where(InventoryDraft.status == status)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.scalars(
        query.order_by(InventoryDraft.updated_at.desc(), InventoryDraft.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return {"items": [response(draft) for draft in items], "total": total}


def create(session: Session, actor: User, session_hash: str, payload: DraftCreate):
    values = normalize_payload(payload.document_type, payload.payload)
    # A stable global key also serializes a same-UUID request by another owner.
    stock_service.lock_command(session, uuid.UUID(int=0), "draft-create", payload.id)
    revalidate_mutation(session, actor, session_hash, DRAFT_PERMISSIONS[payload.document_type])
    previous = session.get(InventoryDraft, payload.id)
    if previous:
        if previous.owner_id != actor.id:
            fail(404, "draft_not_found", "Черновик не найден.")
        if (
            previous.document_type != payload.document_type
            or normalize_payload(previous.document_type, previous.payload) != values
        ):
            fail(
                409,
                "idempotency_conflict",
                "Этот идентификатор уже использован для другого черновика.",
            )
        return response(previous), False
    draft = InventoryDraft(
        id=payload.id, owner_id=actor.id, document_type=payload.document_type, payload=values
    )
    session.add(draft)
    session.flush()
    audit(session, actor.id, "inventory.draft_created", draft.id)
    session.commit()
    return response(draft), True


def require_editable(draft: InventoryDraft):
    if draft.status != "draft":
        fail(409, "draft_not_editable", "Проведённый или архивный черновик нельзя изменить.")


def check_version(draft: InventoryDraft, version: int):
    if draft.version != version:
        fail(409, "version_conflict", "Черновик уже изменён. Обновите данные перед повтором.")


def update(
    session: Session, actor: User, session_hash: str, draft_id: uuid.UUID, payload: DraftUpdate
):
    draft = own_draft(session, actor, draft_id, lock=True)
    revalidate_mutation(session, actor, session_hash, DRAFT_PERMISSIONS[draft.document_type])
    require_editable(draft)
    values = normalize_payload(draft.document_type, payload.payload)
    if (
        draft.version == payload.version + 1
        and normalize_payload(draft.document_type, draft.payload) == values
    ):
        # The previous save committed but its response was lost; preserve its version.
        return response(draft)
    check_version(draft, payload.version)
    draft.payload = values
    draft.version += 1
    draft.updated_at = datetime.now(UTC)
    audit(session, actor.id, "inventory.draft_updated", draft.id)
    session.commit()
    return response(draft)


def archive(session: Session, actor: User, session_hash: str, draft_id: uuid.UUID, version: int):
    draft = own_draft(session, actor, draft_id, lock=True)
    revalidate_mutation(session, actor, session_hash, DRAFT_PERMISSIONS[draft.document_type])
    if draft.status == "archived" and draft.version == version + 1:
        return response(draft)
    require_editable(draft)
    check_version(draft, version)
    draft.status = "archived"
    draft.archived_at = datetime.now(UTC)
    draft.version += 1
    audit(session, actor.id, "inventory.draft_archived", draft.id)
    session.commit()
    return response(draft)


def post(session: Session, actor: User, session_hash: str, draft_id: uuid.UUID, version: int):
    # No warehouse command locks a draft after an item, so this precedes conduct's order.
    draft = own_draft(session, actor, draft_id, lock=True)
    if draft.status == "posted":
        revalidate_mutation(session, actor, session_hash, DRAFT_PERMISSIONS[draft.document_type])
        return {
            "draft": response(draft),
            "document": document_response(session, get_document(session, draft.posted_document_id)),
        }, False
    require_editable(draft)
    check_version(draft, version)
    schema = ReceiptInput if draft.document_type == "receipt" else IssueInput
    try:
        payload = schema.model_validate(draft.payload)
    except ValidationError:
        fail(
            422,
            "draft_incomplete",
            "Заполните дату, получателя и строки документа перед проведением.",
        )
    document, _ = stock_service.conduct(
        session, actor, session_hash, draft.id, payload, commit=False
    )
    draft.status = "posted"
    draft.posted_document_id = document["id"]
    draft.version += 1
    draft.updated_at = datetime.now(UTC)
    audit(session, actor.id, "inventory.draft_posted", draft.id)
    session.flush()
    result = {"draft": response(draft), "document": document}
    session.commit()
    return result, True
