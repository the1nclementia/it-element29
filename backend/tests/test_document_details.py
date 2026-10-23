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


def test_equipment_upgrade_preserves_0005_documents_photos_and_drafts(empty_database):
    """The 0007 extension must add equipment without rewriting stage-2 data."""
    engine, _, config = empty_database
    command.upgrade(config, "0005_inventory_document_details")
    actor_id = uuid.uuid4()
    manufacturer_id, item_id = uuid.uuid4(), uuid.uuid4()
    document_id, document_item_id, movement_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    file_id, attachment_id, draft_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with Session(engine) as session:
        actor = bootstrap_admin(
            session,
            "migration_equipment",
            "Синтетический оператор",
            "Synthetic-migration-password-2026",
        )
        actor_id = actor.id
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO manufacturers (id, name, name_key) VALUES (:id, :name, :key)"),
            {"id": manufacturer_id, "name": "Старый производитель", "key": "старый производитель"},
        )
        connection.execute(
            text(
                "INSERT INTO inventory_items "
                "(id, internal_code, category_id, manufacturer_id, model, min_stock) "
                "VALUES (:id, 'LEGACY-MONITOR', "
                "'00000000-0000-0000-0000-000000000029', :manufacturer, 'Старая модель', 0)"
            ),
            {"id": item_id, "manufacturer": manufacturer_id},
        )
        connection.execute(
            text(
                "INSERT INTO inventory_documents "
                "(id, number, document_type, document_date, created_by_id, "
                "idempotency_key, request_hash, supplier_name) "
                "VALUES (:id, 'INV-LEGACY-0005', 'receipt', '2026-10-22', "
                ":actor, :key, :hash, 'Старый поставщик')"
            ),
            {"id": document_id, "actor": actor_id, "key": uuid.uuid4(), "hash": "b" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO inventory_document_items "
                "(id, document_id, inventory_item_id, quantity, line_number, "
                "internal_code, model, manufacturer) "
                "VALUES (:id, :document, :item, 2, 1, 'LEGACY-MONITOR', "
                "'Старая модель', 'Старый производитель')"
            ),
            {"id": document_item_id, "document": document_id, "item": item_id},
        )
        connection.execute(
            text(
                "INSERT INTO inventory_movements (id, document_item_id, inventory_item_id, delta) "
                "VALUES (:id, :document_item, :item, 2)"
            ),
            {"id": movement_id, "document_item": document_item_id, "item": item_id},
        )
        connection.execute(
            text(
                "INSERT INTO file_attachments "
                "(id, storage_key, mime_type, size, sha256, width, height, uploaded_by_id) "
                "VALUES (:id, 'legacy/photo.png', 'image/png', 128, :sha, 16, 16, :actor)"
            ),
            {"id": file_id, "sha": "c" * 64, "actor": actor_id},
        )
        connection.execute(
            text(
                "INSERT INTO inventory_item_attachments "
                "(id, inventory_item_id, file_attachment_id, position, is_primary) "
                "VALUES (:id, :item, :file, 0, true)"
            ),
            {"id": attachment_id, "item": item_id, "file": file_id},
        )
        connection.execute(
            text(
                "INSERT INTO inventory_drafts (id, owner_id, document_type, payload) "
                "VALUES (:id, :actor, 'receipt', CAST(:payload AS jsonb))"
            ),
            {
                "id": draft_id,
                "actor": actor_id,
                "payload": (
                    '{"items": [{"inventory_item_id": "LEGACY-MONITOR", '
                    '"quantity": 1}], "comment": "Фото сохранено"}'
                ),
            },
        )
    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert "equipment_instances" in inspector.get_table_names()
    with engine.connect() as connection:
        document = (
            connection.execute(
                text("SELECT number, supplier_name FROM inventory_documents WHERE id=:id"),
                {"id": document_id},
            )
            .mappings()
            .one()
        )
        assert document == {"number": "INV-LEGACY-0005", "supplier_name": "Старый поставщик"}
        assert (
            connection.scalar(
                text("SELECT count(*) FROM inventory_movements WHERE id=:id"), {"id": movement_id}
            )
            == 1
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM inventory_item_attachments WHERE id=:id"),
                {"id": attachment_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                text("SELECT status FROM inventory_drafts WHERE id=:id"), {"id": draft_id}
            )
            == "draft"
        )
        item = (
            connection.execute(
                text("SELECT accounting_mode, item_type FROM inventory_items WHERE id=:id"),
                {"id": item_id},
            )
            .mappings()
            .one()
        )
        assert item == {"accounting_mode": "quantity", "item_type": "cartridge"}
