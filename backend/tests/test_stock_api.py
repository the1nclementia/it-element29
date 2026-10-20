import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_stock import PASSWORD, balance, headers, post, receive, wait_for_locks
from test_stock import stock as stock

from app.main import create_app
from app.modules.directory.models import Employee
from app.modules.inventory.models import InventoryItem

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("role", ["administrator", "storekeeper", "it_specialist", "manager"])
def test_stock_http_permissions_for_every_role(stock, role):
    browser, _, settings, ids = stock
    receive(stock)
    created = browser.post(
        "/api/v1/users",
        headers=headers(browser),
        json={
            "username": "role_" + role,
            "display_name": "Тестовая роль",
            "role": role,
            "password": PASSWORD,
        },
    )
    assert created.status_code == 201
    with TestClient(create_app(settings)) as member:
        assert (
            member.post(
                "/api/v1/auth/login",
                headers=headers(member),
                json={
                    "username": "role_" + role,
                    "password": PASSWORD,
                },
            ).status_code
            == 200
        )
        assert member.get("/api/v1/inventory/documents").status_code == 403
        assert (
            member.post(
                "/api/v1/auth/password",
                headers=headers(member),
                json={
                    "current_password": PASSWORD,
                    "new_password": PASSWORD + "-changed",
                },
            ).status_code
            == 200
        )
        assert member.get("/api/v1/inventory/documents").status_code == 200
        assert member.get("/api/v1/directory/employees").status_code == 200
        can_manage = role in {"administrator", "storekeeper"}
        assert post(member, "receipts", [(ids["items"][0], 2)]).status_code == (
            201 if can_manage else 403
        )
        issued = post(member, "issues", [(ids["items"][0], 1)], employee=ids["employee"])
        assert issued.status_code == (403 if role == "manager" else 201)
        target = browser.get("/api/v1/inventory/documents").json()["items"][0]["id"]
        cancelled = member.post(
            f"/api/v1/inventory/documents/{target}/cancel",
            headers=headers(member),
            json={"reason": "Тест права отмены"},
        )
        assert cancelled.status_code == (201 if can_manage else 403)
        department = member.post(
            "/api/v1/directory/departments",
            headers=headers(member),
            json={"code": "ROLE-TEST", "name": "Тестовое подразделение"},
        )
        assert department.status_code == (201 if role == "administrator" else 403)


def test_stock_validation_archives_and_anonymous_access(stock):
    browser, engine, settings, ids = stock
    payload = {
        "document_date": "2026-10-19",
        "items": [{"inventory_item_id": ids["items"][0], "quantity": 1}],
    }
    h = headers(browser)
    h.pop("Idempotency-Key")
    assert browser.post("/api/v1/inventory/receipts", headers=h, json=payload).status_code == 422
    for quantity in (0, -1, True, 1.5, "2"):
        assert post(browser, "receipts", [(ids["items"][0], quantity)]).status_code == 422
    assert post(browser, "receipts", []).status_code == 422
    assert post(browser, "receipts", [(ids["items"][0], 1)] * 2).status_code == 422
    assert post(browser, "receipts", [(str(uuid.uuid4()), 1)]).status_code == 404
    with TestClient(create_app(settings)) as anonymous:
        assert anonymous.get("/api/v1/inventory/documents").status_code == 401
        assert (
            anonymous.post(
                "/api/v1/inventory/receipts", headers=headers(anonymous), json=payload
            ).status_code
            == 401
        )
    item = browser.get(f"/api/v1/inventory/items/{ids['items'][0]}").json()
    assert (
        browser.post(
            f"/api/v1/inventory/items/{item['id']}/archive",
            headers=headers(browser),
            json={"version": item["version"]},
        ).status_code
        == 200
    )
    assert post(browser, "receipts", [(item["id"], 1)]).status_code == 409
    with Session(engine) as session:
        employee = session.get(Employee, uuid.UUID(ids["employee"]))
        employee.archived_at = datetime.now(UTC)
        session.commit()
    assert (
        post(browser, "issues", [(ids["items"][1], 1)], employee=ids["employee"]).status_code == 409
    )


def test_document_filters_canonical_replay_movements_and_dashboard(stock):
    browser, _, _, ids = stock
    receipt = receive(stock)
    key = uuid.uuid4()
    lines = [(ids["items"][0], 1), (ids["items"][1], 2)]
    issued = post(browser, "issues", lines, employee=ids["employee"], key=key).json()
    repeated = post(browser, "issues", list(reversed(lines)), employee=ids["employee"], key=key)
    assert repeated.status_code == 200 and repeated.json()["id"] == issued["id"]
    filtered = browser.get(
        "/api/v1/inventory/documents",
        params={
            "document_type": "issue",
            "recipient_employee_id": ids["employee"],
            "date_from": "2026-10-18",
            "date_to": "2026-10-18",
            "created_by_id": str(ids["admin"]),
            "cancelled": "false",
        },
    )
    assert filtered.status_code == 200
    assert [row["id"] for row in filtered.json()["items"]] == [issued["id"]]
    assert filtered.json()["total"] == 1
    assert (
        browser.get(
            "/api/v1/inventory/documents",
            params={"date_from": "2026-10-19", "date_to": "2026-10-18"},
        ).status_code
        == 422
    )
    assert browser.get("/api/v1/inventory/documents", params={"limit": 101}).status_code == 422
    assert (
        browser.get("/api/v1/inventory/documents", params={"limit": 1, "offset": 1}).json()["total"]
        == 2
    )
    movements = browser.get(f"/api/v1/inventory/items/{ids['items'][0]}/movements").json()
    assert movements["total"] == 2
    assert [row["delta"] for row in movements["items"]] == [-1, 10]
    assert movements["items"][1]["document_id"] == receipt["id"]
    metrics = browser.get("/api/v1/dashboard").json()["metrics"]
    assert next(m for m in metrics if m["key"] == "issues_today")["value"] == 1
    assert (
        browser.post(
            f"/api/v1/inventory/documents/{issued['id']}/cancel",
            headers=headers(browser),
            json={"reason": "Проверка отменённого документа"},
        ).status_code
        == 201
    )
    metrics = browser.get("/api/v1/dashboard").json()["metrics"]
    assert next(m for m in metrics if m["key"] == "issues_today")["value"] == 0
    assert (
        browser.get("/api/v1/inventory/documents", params={"cancelled": "true"}).json()["total"]
        == 1
    )


def test_lock_timeout_is_safe_and_same_key_can_be_retried(stock):
    browser, engine, _, ids = stock
    receive(stock)
    h = headers(browser)
    payload = {
        "document_date": "2026-10-19",
        "recipient_employee_id": ids["employee"],
        "items": [{"inventory_item_id": ids["items"][0], "quantity": 1}],
    }
    with ThreadPoolExecutor(max_workers=1) as pool:
        with engine.begin() as blocker:
            blocker.execute(
                select(InventoryItem.id)
                .where(InventoryItem.id == uuid.UUID(ids["items"][0]))
                .with_for_update()
            )
            pending = pool.submit(browser.post, "/api/v1/inventory/issues", headers=h, json=payload)
            wait_for_locks(blocker, 1)
            result = pending.result(timeout=5)
            assert result.status_code == 503
            assert result.json()["detail"]["code"] == "operation_busy"
            assert "SELECT" not in result.text and ids["items"][0] not in result.text
    assert balance(engine, ids["items"][0]) == 10
    assert browser.post("/api/v1/inventory/issues", headers=h, json=payload).status_code == 201
    assert balance(engine, ids["items"][0]) == 9
