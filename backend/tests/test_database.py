"""Runs only against a disposable database ending in _test; never uses SQLite."""

from typing import Annotated

import pytest
from alembic import command
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import create_app
from app.modules.directory.models import Department, Employee, Location

pytestmark = pytest.mark.integration


def test_request_session_does_not_implicitly_commit(database):
    engine, settings, _ = database
    app = create_app(settings)

    @app.post("/test-transaction")
    def uncommitted_insert(session: Annotated[Session, Depends(get_session)]):
        session.add(Department(code="REQUEST-ROLLBACK", name="Незафиксированная запись"))
        session.flush()
        return {"flushed": True}

    with TestClient(app) as client:
        assert client.post("/test-transaction").status_code == 200
    with Session(engine) as session:
        assert (
            session.scalar(select(Department).where(Department.code == "REQUEST-ROLLBACK")) is None
        )


def test_migration_uses_verified_database_instead_of_ambient_environment(database, monkeypatch):
    _, _, config = database
    monkeypatch.setenv("POSTGRES_PORT", "1")
    monkeypatch.setenv("POSTGRES_PASSWORD", "wrong-ambient-password")
    # Must connect to the fixture's validated database, not ambient settings.
    command.check(config)


def test_migration_schema_constraints_and_transaction_rollback(database):
    engine, _, config = database
    command.check(config)
    with Session(engine) as session:
        department = Department(code="TEST-IT", name="Тестовый отдел")
        session.add(department)
        session.flush()
        employee = Employee(
            personnel_number="TEST-001",
            full_name="Вымышленный сотрудник",
            department_id=department.id,
        )
        session.add(employee)
        session.flush()
        assert employee.created_at.utcoffset().total_seconds() == 0
        session.add(Location(code="TEST-STOCK", name="Тестовый склад", department_id=department.id))
        session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(Department(code="TEST-IT", name="Дубликат"))
            session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(Department(code="   ", name="Пустой код"))
            session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.delete(department)
            session.flush()
        # No commit: closing this transaction must roll back all three inserts.
    with Session(engine) as session:
        assert session.scalar(select(Department).where(Department.code == "TEST-IT")) is None


def test_ready_only_after_forward_migration(empty_database):
    engine, settings, config = empty_database
    with TestClient(create_app(settings)) as client:
        assert "departments" not in inspect(engine).get_table_names()
        assert client.get("/api/v1/health/ready").status_code == 503
        assert client.get("/api/v1/health/live").status_code == 200
        command.upgrade(config, "head")
        assert client.get("/api/v1/health/ready").status_code == 200
