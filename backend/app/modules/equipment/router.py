import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from app.modules.equipment import movement_service, service
from app.modules.equipment.movement_schemas import EquipmentMoveInput
from app.modules.equipment.schemas import EquipmentInstanceCreate, EquipmentInstancePatch
from app.modules.identity.dependencies import CsrfSession, Database, require_permission
from app.modules.identity.models import User
from app.modules.inventory.schemas import VersionInput

router = APIRouter(prefix="/equipment", tags=["Оборудование"])
Reader = Annotated[User, Depends(require_permission("equipment.read"))]
Manager = Annotated[User, Depends(require_permission("equipment.manage"))]
MovementReader = Annotated[User, Depends(require_permission("movements.read"))]
MovementManager = Annotated[User, Depends(require_permission("movements.manage"))]


@router.get("/instances")
def list_instances(
    session: Database,
    actor: Reader,
    q: str = Query(default="", max_length=100),
    inventory_item_id: uuid.UUID | None = None,
    archived: str = "false",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    if archived not in {"false", "true", "all"}:
        from app.modules.identity.errors import fail

        fail(422, "invalid_archived", "Параметр archived имеет недопустимое значение.")
    return service.list_instances(
        session,
        q=q,
        inventory_item_id=inventory_item_id,
        archived=archived,
        offset=offset,
        limit=limit,
    )


@router.post("/instances", status_code=201)
def create_instance(
    payload: EquipmentInstanceCreate,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.create(session, actor, csrf.token_hash, payload)


@router.patch("/instances/{instance_id}")
def update_instance(
    instance_id: uuid.UUID,
    payload: EquipmentInstancePatch,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.update(session, actor, csrf.token_hash, instance_id, payload)


@router.post("/instances/{instance_id}/archive")
def archive_instance(
    instance_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive(session, actor, csrf.token_hash, instance_id, payload.version, True)


@router.post("/instances/{instance_id}/restore")
def restore_instance(
    instance_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive(session, actor, csrf.token_hash, instance_id, payload.version, False)


@router.post("/movements", status_code=201)
def move_instances(
    payload: EquipmentMoveInput,
    session: Database,
    actor: MovementManager,
    csrf: CsrfSession,
    key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
    response: Response,
):
    result, created = movement_service.move(session, actor, csrf.token_hash, key, payload)
    response.status_code = 201 if created else 200
    return result


@router.get("/movements")
def movement_history(
    session: Database,
    actor: MovementReader,
    instance_id: uuid.UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    return movement_service.history(session, instance_id, offset, limit)
