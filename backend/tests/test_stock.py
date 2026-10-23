import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.provision import provision_runtime_role
from app.main import create_app
from app.modules.directory.models import Department, Employee
from app.modules.identity.models import AuditLog
from app.modules.identity.service import bootstrap_admin
from app.modules.inventory.models import (
    InventoryCategory,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryItem,
    InventoryMovement,
    Manufacturer,
)

pytestmark = pytest.mark.integration
PASSWORD = "Synthetic-stock-password-2026"
ORIGIN = {"Origin": "http://testserver"}


def headers(browser, key=None):
    result = browser.get("/api/v1/auth/csrf")
    assert result.status_code == 200
    return {
        **ORIGIN,
        "X-CSRF-Token": result.json()["csrf_token"],
        "Idempotency-Key": str(key or uuid.uuid4()),
    }


def login(browser):
    result = browser.post(
        "/api/v1/auth/login",
        headers=headers(browser),
        json={"username": "stock_admin", "password": PASSWORD},
    )
    assert result.status_code == 200, result.text
    return result.json()["user"]


@pytest.fixture()
def stock(database):
    engine, settings, _ = database
    with Session(engine, expire_on_commit=False) as session:
        admin = bootstrap_admin(session, "stock_admin", "Оператор тестового склада", PASSWORD)
        manufacturer = Manufacturer(name="Тестовый расходник", name_key="тестовый расходник")
        category = session.scalar(
            select(InventoryCategory).where(InventoryCategory.code == "cartridges")
        )
        department = Department(code="STOCK-TEST", name="Отдел для выдачи")
        session.add_all([manufacturer, department])
        session.flush()
        employee = Employee(
            personnel_number="STOCK-01",
            full_name="Вымышленный получатель",
            department_id=department.id,
        )
        items = [
            InventoryItem(
                internal_code=f"STOCK-{i}",
                category_id=category.id,
                manufacturer_id=manufacturer.id,
                model=f"Картридж {i}",
                description="",
                min_stock=2,
            )
            for i in range(2)
        ]
        session.add_all([employee, *items])
        session.commit()
        ids = {
            "items": [str(item.id) for item in items],
            "employee": str(employee.id),
            "department": str(department.id),
            "admin": admin.id,
        }
    role = "stock_runtime_" + uuid.uuid4().hex[:12]
    with engine.begin() as connection:
        provision_runtime_role(connection, role, PASSWORD + "-runtime")
    limited = settings.model_copy(
        update={
            "postgres_user": role,
            "postgres_password": settings.postgres_password.__class__(PASSWORD + "-runtime"),
        }
    )
    with TestClient(create_app(limited)) as browser:
        login(browser)
        yield browser, engine, limited, ids


def post(browser, command, items, *, employee=None, key=None, **fields):
    data = {
        "document_date": date(2026, 10, 18).isoformat(),
        "items": [{"inventory_item_id": item, "quantity": count} for item, count in items],
        **fields,
    }
    if command == "issues":
        if employee is not None:
            data["recipient_employee_id"] = employee
    return browser.post(f"/api/v1/inventory/{command}", headers=headers(browser, key), json=data)


def balance(engine, item):
    with Session(engine) as session:
        return session.scalar(
            select(func.coalesce(func.sum(InventoryMovement.delta), 0)).where(
                InventoryMovement.inventory_item_id == uuid.UUID(item)
            )
        )


def receive(stock, quantities=(10, 10)):
    browser, _, _, ids = stock
    response = post(browser, "receipts", list(zip(ids["items"], quantities, strict=True)))
    assert response.status_code == 201, response.text
    return response.json()


def test_receipt_issue_replay_and_cancel(stock):
    browser, engine, _, ids = stock
    receipt = receive(stock)
    assert len(receipt["items"]) == 2
    key = uuid.uuid4()
    issued = post(browser, "issues", [(ids["items"][0], 3)], employee=ids["employee"], key=key)
    assert issued.status_code == 201, issued.text
    assert balance(engine, ids["items"][0]) == 7
    replay = post(browser, "issues", [(ids["items"][0], 3)], employee=ids["employee"], key=key)
    assert replay.status_code == 200
    assert replay.json()["id"] == issued.json()["id"]
    conflict = post(browser, "issues", [(ids["items"][0], 2)], employee=ids["employee"], key=key)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    cancel_key = uuid.uuid4()
    path = f"/api/v1/inventory/documents/{issued.json()['id']}/cancel"
    cancelled = browser.post(
        path, headers=headers(browser, cancel_key), json={"reason": "Ошибка тестового документа"}
    )
    assert cancelled.status_code == 201, cancelled.text
    assert balance(engine, ids["items"][0]) == 10
    assert (
        browser.post(
            path,
            headers=headers(browser, cancel_key),
            json={"reason": "Ошибка тестового документа"},
        ).status_code
        == 200
    )
    assert (
        browser.post(path, headers=headers(browser), json={"reason": "Другая отмена"}).status_code
        == 409
    )
    assert (
        browser.post(
            f"/api/v1/inventory/documents/{cancelled.json()['id']}/cancel",
            headers=headers(browser),
            json={"reason": "Отмена отмены"},
        ).status_code
        == 409
    )
    original = browser.get(f"/api/v1/inventory/documents/{issued.json()['id']}").json()
    assert original["is_cancelled"] and original["reversal_id"] == cancelled.json()["id"]
    assert original["items"][0]["delta"] == -3


def test_insufficient_one_line_rolls_back_entire_document(stock):
    browser, engine, _, ids = stock
    receive(stock, (5, 2))
    with Session(engine) as session:
        before = [
            session.scalar(select(func.count()).select_from(model))
            for model in [InventoryDocument, InventoryDocumentItem, InventoryMovement, AuditLog]
        ]
    result = post(
        browser, "issues", [(ids["items"][0], 4), (ids["items"][1], 3)], employee=ids["employee"]
    )
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "insufficient_stock"
    assert [balance(engine, item) for item in ids["items"]] == [5, 2]
    with Session(engine) as session:
        after = [
            session.scalar(select(func.count()).select_from(model))
            for model in [InventoryDocument, InventoryDocumentItem, InventoryMovement, AuditLog]
        ]
    assert after == before


def test_receipt_cannot_be_cancelled_when_stock_was_used(stock):
    browser, engine, _, ids = stock
    receipt = receive(stock, (5, 5))
    assert (
        post(browser, "issues", [(ids["items"][0], 5)], employee=ids["employee"]).status_code == 201
    )
    response = browser.post(
        f"/api/v1/inventory/documents/{receipt['id']}/cancel",
        headers=headers(browser),
        json={"reason": "Проверка нехватки"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "insufficient_stock"
    assert [balance(engine, item) for item in ids["items"]] == [0, 5]


def wait_for_locks(blocker, count):
    deadline = time.monotonic() + 2
    while (
        blocker.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND wait_event_type='Lock' AND pid<>pg_backend_pid()"
            )
        )
        < count
    ):
        assert time.monotonic() < deadline, "Requests did not reach the controlled lock barrier"
        time.sleep(0.01)


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_issue_and_idempotency(stock, same_key):
    browser, engine, settings, ids = stock
    receive(stock, (5, 5))
    with TestClient(create_app(settings)) as second:
        login(second)
        key = uuid.uuid4()
        h1, h2 = headers(browser, key), headers(second, key if same_key else None)
        data = {
            "document_date": "2026-10-18",
            "recipient_employee_id": ids["employee"],
            "items": [{"inventory_item_id": ids["items"][0], "quantity": 4}],
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            with engine.begin() as blocker:
                blocker.execute(
                    select(InventoryItem.id)
                    .where(InventoryItem.id == uuid.UUID(ids["items"][0]))
                    .with_for_update()
                )
                a = pool.submit(browser.post, "/api/v1/inventory/issues", headers=h1, json=data)
                b = pool.submit(second.post, "/api/v1/inventory/issues", headers=h2, json=data)
                wait_for_locks(blocker, 2)
            results = [a.result(timeout=5), b.result(timeout=5)]
        assert sorted(r.status_code for r in results) == ([200, 201] if same_key else [201, 409])
    assert balance(engine, ids["items"][0]) == 1
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(InventoryDocument)
                .where(InventoryDocument.document_type == "issue")
            )
            == 1
        )


def test_opposite_line_order_and_concurrent_cancellation(stock):
    browser, engine, settings, ids = stock
    receive(stock, (10, 10))
    with TestClient(create_app(settings)) as second:
        login(second)
        h1, h2 = headers(browser), headers(second)
        lines = [{"inventory_item_id": item, "quantity": 2} for item in ids["items"]]
        data = {
            "document_date": "2026-10-18",
            "recipient_employee_id": ids["employee"],
            "items": lines,
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            with engine.begin() as blocker:
                blocker.execute(
                    select(InventoryItem.id)
                    .where(InventoryItem.id.in_([uuid.UUID(i) for i in ids["items"]]))
                    .order_by(InventoryItem.id)
                    .with_for_update()
                )
                a = pool.submit(browser.post, "/api/v1/inventory/issues", headers=h1, json=data)
                b = pool.submit(
                    second.post,
                    "/api/v1/inventory/issues",
                    headers=h2,
                    json={**data, "items": list(reversed(lines))},
                )
                wait_for_locks(blocker, 2)
            results = [a.result(timeout=5), b.result(timeout=5)]
        assert [r.status_code for r in results] == [201, 201]
        target = results[0].json()["id"]
        h1, h2 = headers(browser), headers(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            with engine.begin() as blocker:
                blocker.execute(
                    select(InventoryItem.id)
                    .where(InventoryItem.id.in_([uuid.UUID(i) for i in ids["items"]]))
                    .order_by(InventoryItem.id)
                    .with_for_update()
                )
                path = f"/api/v1/inventory/documents/{target}/cancel"
                a = pool.submit(browser.post, path, headers=h1, json={"reason": "Первая отмена"})
                b = pool.submit(second.post, path, headers=h2, json={"reason": "Вторая отмена"})
                wait_for_locks(blocker, 2)
            assert sorted([a.result(timeout=5).status_code, b.result(timeout=5).status_code]) == [
                201,
                409,
            ]
    assert [balance(engine, item) for item in ids["items"]] == [8, 8]


def test_waiting_issue_rechecks_revoked_session(stock):
    browser, engine, settings, ids = stock
    receive(stock)
    with TestClient(create_app(settings)) as second:
        login(second)
        h1, h2 = headers(browser), headers(second)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with engine.begin() as blocker:
                blocker.execute(
                    select(InventoryItem.id)
                    .where(InventoryItem.id == uuid.UUID(ids["items"][0]))
                    .with_for_update()
                )
                pending = pool.submit(
                    browser.post,
                    "/api/v1/inventory/issues",
                    headers=h1,
                    json={
                        "document_date": "2026-10-18",
                        "recipient_employee_id": ids["employee"],
                        "items": [{"inventory_item_id": ids["items"][0], "quantity": 2}],
                    },
                )
                wait_for_locks(blocker, 1)
                assert (
                    second.post(
                        "/api/v1/auth/password",
                        headers=h2,
                        json={"current_password": PASSWORD, "new_password": PASSWORD + "-changed"},
                    ).status_code
                    == 200
                )
            assert pending.result(timeout=5).status_code == 401
    assert balance(engine, ids["items"][0]) == 10


def test_audit_insert_failure_rolls_back_document_and_movements(stock, monkeypatch):
    from app.modules.inventory import stock_service

    browser, engine, _, ids = stock
    receive(stock)

    def broken_audit(session, actor_id, action, target_id=None, changes=None):
        session.add(AuditLog(actor_id=actor_id, action=None, changes={}))

    monkeypatch.setattr(stock_service, "audit", broken_audit)
    result = post(browser, "issues", [(ids["items"][0], 2)], employee=ids["employee"])
    assert result.status_code == 503
    assert "INSERT" not in result.text and "password" not in result.text
    assert balance(engine, ids["items"][0]) == 10
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(InventoryDocument)
                .where(InventoryDocument.document_type == "issue")
            )
            == 0
        )


def test_history_snapshots_and_restore_archived_item(stock):
    browser, engine, _, ids = stock
    receive(stock, (3, 1))
    issued = post(browser, "issues", [(ids["items"][0], 3)], employee=ids["employee"])
    assert issued.status_code == 201
    original = issued.json()
    with Session(engine) as session:
        session.get(Employee, uuid.UUID(ids["employee"])).full_name = "Переименованный получатель"
        session.get(Department, uuid.UUID(ids["department"])).name = "Новое подразделение"
        session.get(InventoryItem, uuid.UUID(ids["items"][0])).model = "Другая модель"
        session.commit()
    fetched = browser.get(f"/api/v1/inventory/documents/{original['id']}").json()
    assert fetched["recipient_name"] == "Вымышленный получатель"
    assert fetched["recipient_department"] == "Отдел для выдачи"
    assert fetched["items"][0]["model"] == "Картридж 0"
    item = browser.get(f"/api/v1/inventory/items/{ids['items'][0]}").json()
    assert (
        browser.post(
            f"/api/v1/inventory/items/{ids['items'][0]}/archive",
            headers=headers(browser),
            json={"version": item["version"]},
        ).status_code
        == 200
    )
    assert (
        browser.post(
            f"/api/v1/inventory/documents/{original['id']}/cancel",
            headers=headers(browser),
            json={"reason": "Ошибка выдачи"},
        ).status_code
        == 201
    )
    assert browser.get(f"/api/v1/inventory/items/{ids['items'][0]}").json()["archived_at"] is None
    assert balance(engine, ids["items"][0]) == 3


def test_manual_recipient_issue_preserves_text_snapshots_without_employee(stock):
    browser, engine, _, ids = stock
    receive(stock, (ids["items"][0], 2))
    response = post(
        browser,
        "issues",
        [(ids["items"][0], 1)],
        employee=None,
        recipient_name="  Ручной получатель  ",
        recipient_building=" Корпус А ",
        recipient_department=" ИТ ",
        recipient_room=" 305 ",
    )
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["recipient_employee_id"] is None
    assert document["recipient_name"] == "Ручной получатель"
    assert document["recipient_building"] == "Корпус А"
    assert document["recipient_department"] == "ИТ"
    assert document["recipient_room"] == "305"


def test_runtime_cannot_mutate_ledger_and_dashboard_uses_real_stock(stock):
    browser, engine, settings, ids = stock
    receive(stock, (10, 1))
    metrics = {m["key"]: m for m in browser.get("/api/v1/dashboard").json()["metrics"]}
    assert metrics["cartridge_balance"]["value"] == 11
    assert metrics["low_stock"]["value"] == 1
    assert metrics["issues_today"]["value"] == 0
    assert metrics["equipment_total"]["value"] is None
    with engine.connect() as connection:
        for table in [
            "inventory_documents",
            "inventory_document_items",
            "inventory_movements",
            "audit_logs",
        ]:
            for privilege in ["UPDATE", "DELETE"]:
                assert (
                    connection.scalar(
                        text("SELECT has_table_privilege(:role, :table, :privilege)"),
                        {"role": settings.postgres_user, "table": table, "privilege": privilege},
                    )
                    is False
                )
