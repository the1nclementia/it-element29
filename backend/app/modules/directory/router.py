import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.directory import service
from app.modules.directory.models import Department, Employee
from app.modules.directory.schemas import (
    DepartmentCreate,
    DepartmentPatch,
    EmployeeCreate,
    EmployeePatch,
)
from app.modules.identity.dependencies import CsrfSession, Database, require_permission
from app.modules.identity.models import User
from app.modules.inventory.router import Archived
from app.modules.inventory.schemas import VersionInput

router = APIRouter(prefix="/directory", tags=["Подразделения и сотрудники"])
Reader = Annotated[User, Depends(require_permission("inventory.read"))]
Manager = Annotated[User, Depends(require_permission("directory.manage"))]


@router.get("/departments")
def departments(
    session: Database,
    actor: Reader,
    q: str = Query(default="", max_length=100),
    archived: Archived = "false",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    return service.list_records(
        session, Department, q=q, archived=archived, offset=offset, limit=limit
    )


@router.post("/departments", status_code=201)
def create_department(
    payload: DepartmentCreate, session: Database, actor: Manager, csrf: CsrfSession
):
    return service.save(session, actor, csrf.token_hash, Department, payload)


@router.patch("/departments/{record_id}")
def update_department(
    record_id: uuid.UUID,
    payload: DepartmentPatch,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.save(session, actor, csrf.token_hash, Department, payload, record_id)


@router.post("/departments/{record_id}/archive")
def archive_department(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive(
        session, actor, csrf.token_hash, Department, record_id, payload.version, True
    )


@router.post("/departments/{record_id}/restore")
def restore_department(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive(
        session, actor, csrf.token_hash, Department, record_id, payload.version, False
    )


@router.get("/employees")
def employees(
    session: Database,
    actor: Reader,
    q: str = Query(default="", max_length=100),
    department_id: uuid.UUID | None = None,
    archived: Archived = "false",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    return service.list_records(
        session,
        Employee,
        q=q,
        department_id=department_id,
        archived=archived,
        offset=offset,
        limit=limit,
    )


@router.post("/employees", status_code=201)
def create_employee(payload: EmployeeCreate, session: Database, actor: Manager, csrf: CsrfSession):
    return service.save(session, actor, csrf.token_hash, Employee, payload)


@router.patch("/employees/{record_id}")
def update_employee(
    record_id: uuid.UUID,
    payload: EmployeePatch,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.save(session, actor, csrf.token_hash, Employee, payload, record_id)


@router.post("/employees/{record_id}/archive")
def archive_employee(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive(
        session, actor, csrf.token_hash, Employee, record_id, payload.version, True
    )


@router.post("/employees/{record_id}/restore")
def restore_employee(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive(
        session, actor, csrf.token_hash, Employee, record_id, payload.version, False
    )
