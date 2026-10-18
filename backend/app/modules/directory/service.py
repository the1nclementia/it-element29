"""Подразделения и получатели; подразделение блокируется раньше сотрудника."""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.directory.models import Department, Employee
from app.modules.identity.authorization import revalidate_mutation
from app.modules.identity.errors import fail
from app.modules.identity.repository import audit
from app.modules.inventory.catalog_service import base_response, check_version, commit, locked
from app.modules.inventory.repository import archived_filter, escaped_like


def response(session: Session, record):
    result = base_response(record)
    if isinstance(record, Department):
        result.update(code=record.code, name=record.name)
    else:
        result.update(
            personnel_number=record.personnel_number,
            full_name=record.full_name,
            department_id=record.department_id,
            department_name=session.get(Department, record.department_id).name,
        )
    return result


def list_records(
    session: Session, model, *, q="", archived="false", offset=0, limit=20, department_id=None
):
    statement = archived_filter(select(model), model, archived)
    fields = (
        (Department.code, Department.name)
        if model is Department
        else (Employee.personnel_number, Employee.full_name)
    )
    if q:
        statement = statement.where(
            or_(*(field.ilike(escaped_like(q), escape="\\") for field in fields))
        )
    if department_id and model is Employee:
        statement = statement.where(Employee.department_id == department_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    records = session.scalars(statement.order_by(fields[1], model.id).offset(offset).limit(limit))
    return {"items": [response(session, record) for record in records], "total": total}


def save(session: Session, actor, session_hash, model, payload, record_id=None):
    values = payload.model_dump(exclude_unset=True)
    version = values.pop("version", None)
    if model is Department and "code" in values:
        values["code"] = values["code"].upper()
    if model is Employee:
        previous = session.get(Employee, record_id) if record_id else None
        if record_id and previous is None:
            fail(404, "not_found", "Сотрудник не найден.")
        previous_department = previous.department_id if previous else None
        target_department = values.get("department_id", previous_department)
        for department_id in sorted({target_department, previous_department} - {None}, key=str):
            locked(
                session,
                Department,
                department_id,
                active=department_id == target_department,
                shared=True,
            )
    record = locked(session, model, record_id) if record_id else None
    if model is Employee and record and record.department_id != previous_department:
        fail(409, "operation_busy", "Подразделение сотрудника изменилось. Повторите действие.")
    if record:
        check_version(record, version)
        if record.archived_at is not None:
            fail(409, "record_archived", "Сначала восстановите запись из архива.")
    revalidate_mutation(session, actor, session_hash, "directory.manage")
    if record is None:
        record = model(**values)
        session.add(record)
    else:
        for name, value in values.items():
            setattr(record, name, value)
        record.version += 1
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        fail(409, "duplicate_record", "Запись с таким кодом или табельным номером уже существует.")
    audit(
        session,
        actor.id,
        "directory.record_updated" if record_id else "directory.record_created",
        record.id,
        {"fields": sorted(values)},
    )
    commit(session)
    return response(session, record)


def archive(session: Session, actor, session_hash, model, record_id, version, archived):
    if model is Employee:
        previous = session.get(Employee, record_id)
        if previous is None:
            fail(404, "not_found", "Сотрудник не найден.")
        previous_department = previous.department_id
        locked(session, Department, previous_department, active=not archived, shared=True)
    record = locked(session, model, record_id)
    if model is Employee and record.department_id != previous_department:
        fail(409, "operation_busy", "Подразделение сотрудника изменилось. Повторите действие.")
    check_version(record, version)
    revalidate_mutation(session, actor, session_hash, "directory.manage")
    if (
        model is Department
        and archived
        and session.scalar(
            select(Employee.id)
            .where(Employee.department_id == record_id, Employee.archived_at.is_(None))
            .limit(1)
        )
    ):
        fail(
            409,
            "department_has_active_employees",
            "Сначала переведите или архивируйте активных сотрудников подразделения.",
        )
    record.archived_at = datetime.now(UTC) if archived else None
    record.version += 1
    audit(
        session,
        actor.id,
        "directory.record_archived" if archived else "directory.record_restored",
        record.id,
    )
    commit(session)
    return response(session, record)
