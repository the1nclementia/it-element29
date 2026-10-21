"""Сквозная приёмка: черновик не резервирует остаток; проведение атомарно."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_stock import balance, headers, post
from test_stock import stock as stock

from app.modules.inventory.models import InventoryDocument, InventoryMovement

pytestmark = pytest.mark.integration


def test_twenty_received_draft_five_posted_and_sixteen_rejected(stock):
    browser, engine, settings, ids = stock
    item_id = ids["items"][0]
    received = post(browser, "receipts", [(item_id, 20)], supplier_name="Тестовый поставщик")
    assert received.status_code == 201, received.text
    assert balance(engine, item_id) == 20

    payload = {
        "document_date": "2026-10-19",
        "recipient_employee_id": ids["employee"],
        "recipient_room": "201",
        "items": [{"inventory_item_id": item_id, "quantity": 5}],
    }
    created = browser.post(
        "/api/v1/inventory/drafts",
        headers=headers(browser),
        json={"document_type": "issue", "payload": payload},
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    path = "/api/v1/inventory/drafts/" + draft["id"]
    assert browser.get(path).json()["payload"]["items"][0]["quantity"] == 5
    assert balance(engine, item_id) == 20
    assert browser.get("/api/v1/inventory/items/" + item_id).json()["balance"] == 20
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryDocument)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryMovement)) == 1

    posted = browser.post(path + "/post", headers=headers(browser), json={"version": 1})
    assert posted.status_code == 201, posted.text
    document = posted.json()["document"]
    assert document["recipient_name"] == "Вымышленный получатель"
    assert document["recipient_department"] == "Отдел для выдачи"
    assert document["recipient_room"] == "201"
    assert document["items"][0]["quantity"] == 5
    assert document["items"][0]["delta"] == -5
    assert balance(engine, item_id) == 15

    rejected = post(browser, "issues", [(item_id, 16)], employee=ids["employee"])
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "insufficient_stock"
    assert rejected.json()["detail"]["items"] == [
        {"inventory_item_id": item_id, "available": 15, "requested": 16}
    ]
    assert balance(engine, item_id) == 15
    assert browser.get("/api/v1/inventory/items/" + item_id).json()["balance"] == 15
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryDocument)) == 2
        assert session.scalar(select(func.count()).select_from(InventoryMovement)) == 2
        assert (
            session.scalar(
                select(InventoryDocument.created_by_id).where(
                    InventoryDocument.id == uuid.UUID(document["id"])
                )
            )
            == ids["admin"]
        )

    replayed = browser.post(path + "/post", headers=headers(browser), json={"version": 1})
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["document"]["id"] == document["id"]
    assert balance(engine, item_id) == 15
    # The request ran with the minimal application role, not the migration owner.
    assert settings.postgres_user.startswith("stock_runtime_")
