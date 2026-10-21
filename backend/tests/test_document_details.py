"""Снимки реквизитов, совместимость старых запросов и экспорт документов."""

import uuid

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from test_exports import sheet
from test_stock import headers, post
from test_stock import stock as stock

from app.modules.directory.models import Department, Employee
from app.modules.identity.service import bootstrap_admin
from app.modules.inventory.stock_service import request_hash

pytestmark = pytest.mark.integration


def test_document_details_survive_read_cancel_and_export(stock):
    browser, engine, _, ids = stock
    receipt = post(
        browser, "receipts", [(ids["items"][0], 5)], supplier_name="  Тестовый поставщик  "
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["supplier_name"] == "Тестовый поставщик"
    assert receipt.json()["recipient_room"] is None
    issued = post(
        browser,
        "issues",
        [(ids["items"][0], 2)],
        employee=ids["employee"],
        recipient_room="  201-Б  ",
    )
    assert issued.status_code == 201, issued.text
    assert issued.json()["recipient_room"] == "201-Б"
    assert issued.json()["supplier_name"] is None
    with Session(engine) as session:
        session.get(Employee, uuid.UUID(ids["employee"])).full_name = "Новое имя"
        session.get(Department, uuid.UUID(ids["department"])).name = "Новое подразделение"
        session.commit()
    document = browser.get("/api/v1/inventory/documents/" + issued.json()["id"]).json()
    assert document["recipient_name"] == "Вымышленный получатель"
    assert document["recipient_department"] == "Отдел для выдачи"
    assert document["recipient_room"] == "201-Б"
    for original, field, expected in [
        (issued, "recipient_room", "201-Б"),
        (receipt, "supplier_name", "Тестовый поставщик"),
    ]:
        cancelled = browser.post(
            "/api/v1/inventory/documents/" + original.json()["id"] + "/cancel",
            headers=headers(browser),
            json={"reason": "Проверка снимка"},
        )
        assert cancelled.status_code == 201, cancelled.text
        assert cancelled.json()[field] == expected
    rows = sheet(browser.get("/api/v1/inventory/exports/movements.xlsx"))
    supplier_column = rows[0].index("Поставщик (снимок)")
    room_column = rows[0].index("Кабинет (снимок)")
    assert [row[supplier_column] for row in rows[1:]] == [
        "Тестовый поставщик",
        "",
        "",
        "Тестовый поставщик",
    ]
    assert [row[room_column] for row in rows[1:]] == ["", "201-Б", "201-Б", ""]


@pytest.mark.parametrize(
    ("command", "field"), [("receipts", "supplier_name"), ("issues", "recipient_room")]
)
def test_document_details_participate_in_idempotency(stock, command, field):
    browser, _, _, ids = stock
    received = post(browser, "receipts", [(ids["items"][0], 5)])
    assert received.status_code == 201
    key = uuid.uuid4()
    args = {"employee": ids["employee"], "key": key, field: "  Первое значение  "}
    result = post(browser, command, [(ids["items"][0], 1)], **args)
    assert result.status_code == 201, result.text
    args[field] = "Первое значение"
    replay = post(browser, command, [(ids["items"][0], 1)], **args)
    assert replay.status_code == 200 and replay.json()["id"] == result.json()["id"]
    args[field] = "Другое значение"
    conflict = post(browser, command, [(ids["items"][0], 1)], **args)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


def test_optional_details_do_not_change_historic_request_fingerprint():
    original = {"document_date": "2026-10-18", "items": [], "comment": ""}
    assert request_hash(original) == request_hash({**original, "supplier_name": None})
    assert request_hash(original) == request_hash({**original, "recipient_room": None})


def test_details_upgrade_preserves_existing_0004_document_and_draft(empty_database):
    engine, _, config = empty_database
    command.upgrade(config, "0004_inventory_drafts")
    document_id, draft_id, key = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with Session(engine) as session:
        actor = bootstrap_admin(
            session, "migration_details", "Тестовый оператор", "Synthetic-migration-password-2026"
        )
        actor_id = actor.id
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO inventory_documents "
                "(id, number, document_type, document_date, created_by_id, comment, "
                "receipt_purpose, external_number, idempotency_key, request_hash) "
                "VALUES (:id, :number, 'receipt', '2026-10-18', :actor, :comment, "
                "'delivery', :external, :key, :fingerprint)"
            ),
            {
                "id": document_id,
                "number": "INV-LEGACY",
                "actor": actor_id,
                "comment": "Существующее поступление",
                "external": "НК-001",
                "key": key,
                "fingerprint": "a" * 64,
            },
        )
        connection.execute(
            text(
                "INSERT INTO inventory_drafts (id, owner_id, document_type, payload) "
                "VALUES (:id, :owner, 'receipt', CAST(:payload AS jsonb))"
            ),
            {"id": draft_id, "owner": actor_id, "payload": '{"items": [], "comment": "Старый"}'},
        )
    command.upgrade(config, "head")
    columns = {
        column["name"]: column for column in inspect(engine).get_columns("inventory_documents")
    }
    assert columns["supplier_name"]["nullable"] and columns["recipient_room"]["nullable"]
    with engine.connect() as connection:
        stored = (
            connection.execute(
                text("SELECT * FROM inventory_documents WHERE id=:id"), {"id": document_id}
            )
            .mappings()
            .one()
        )
        assert stored["comment"] == "Существующее поступление"
        assert stored["external_number"] == "НК-001" and stored["request_hash"] == "a" * 64
        assert stored["supplier_name"] is None and stored["recipient_room"] is None
        draft = (
            connection.execute(
                text("SELECT payload, version, status FROM inventory_drafts WHERE id=:id"),
                {"id": draft_id},
            )
            .mappings()
            .one()
        )
        assert draft["payload"] == {"items": [], "comment": "Старый"}
        assert draft["version"] == 1 and draft["status"] == "draft"
