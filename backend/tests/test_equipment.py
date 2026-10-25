import uuid

import pytest
from test_catalog import catalog as catalog
from test_catalog import create, headers, item_create, references

pytestmark = pytest.mark.integration


def serialized_item(client, manufacturer, category, code="MONITOR-01"):
    return item_create(
        client,
        manufacturer,
        category,
        code=code,
        model="Dell P2422H",
        accounting_mode="serialized",
        item_type="monitor",
    )


def test_equipment_instances_register_numbers_and_current_state(catalog):
    browser, _ = catalog
    manufacturer, category = references(browser)
    item = serialized_item(browser, manufacturer, category)
    response = browser.post(
        "/api/v1/equipment/instances",
        headers=headers(browser),
        json={
            "inventory_item_id": item["id"],
            "serial_number": "  SN-001 ",
            "inventory_number": " INV-001 ",
            "current_building": " Корпус А ",
        },
    )
    assert response.status_code == 201, response.text
    instance = response.json()
    assert instance["serial_number"] == "SN-001"
    assert instance["inventory_number"] == "INV-001"
    assert instance["current_building"] == "Корпус А"
    assert instance["is_under_repair"] is False
    listed = browser.get("/api/v1/equipment/instances", params={"q": "SN-001"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = browser.patch(
        "/api/v1/equipment/instances/" + instance["id"],
        headers=headers(browser),
        json={"version": 1, "serial_number": "SN-002"},
    )
    assert updated.status_code == 200
    assert updated.json()["serial_number"] == "SN-002"
    archived = browser.post(
        "/api/v1/equipment/instances/" + instance["id"] + "/archive",
        headers=headers(browser),
        json={"version": 2},
    )
    assert archived.status_code == 200
    assert browser.get("/api/v1/equipment/instances").json()["total"] == 0
    assert (
        browser.get("/api/v1/equipment/instances", params={"archived": "true"}).json()["total"] == 1
    )


def test_equipment_instance_identifiers_are_globally_unique_and_optional(catalog):
    browser, _ = catalog
    manufacturer, category = references(browser)
    item = serialized_item(browser, manufacturer, category, "MONITOR-02")
    first = create(
        browser,
        "equipment/instances",
        {"inventory_item_id": item["id"], "serial_number": "SN-DUP", "inventory_number": "INV-DUP"},
    )
    assert first["id"]
    duplicate_inventory = browser.post(
        "/api/v1/equipment/instances",
        headers=headers(browser),
        json={
            "inventory_item_id": item["id"],
            "serial_number": "SN-OTHER",
            "inventory_number": " inv-dup ",
        },
    )
    assert duplicate_inventory.status_code == 409
    duplicate_serial = browser.post(
        "/api/v1/equipment/instances",
        headers=headers(browser),
        json={
            "inventory_item_id": item["id"],
            "serial_number": " sn-dup ",
            "inventory_number": "INV-OTHER",
        },
    )
    assert duplicate_serial.status_code == 409
    assert duplicate_serial.json()["detail"]["code"] == "duplicate_serial_number"
    empty_numbers = create(browser, "equipment/instances", {"inventory_item_id": item["id"]})
    assert empty_numbers["serial_number"] is None
    assert empty_numbers["inventory_number"] is None
    assert empty_numbers["identification_warning"]

    matches = browser.get("/api/v1/equipment/instances", params={"q": "INV-DUP"}).json()
    assert matches["total"] == 1
    assert {row["serial_number"] for row in matches["items"]} == {"SN-DUP"}
    assert browser.get("/api/v1/equipment/instances", params={"q": "SN-OTHER"}).json()[
        "total"
    ] == 0


def test_quantity_item_cannot_register_equipment(catalog):
    browser, _ = catalog
    manufacturer, category = references(browser)
    item = item_create(browser, manufacturer, category, code="QUANTITY-01")
    response = browser.post(
        "/api/v1/equipment/instances",
        headers=headers(browser),
        json={"inventory_item_id": item["id"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "not_serialized_item"


def test_serialized_item_is_excluded_from_quantity_low_stock_and_documents(catalog):
    browser, _ = catalog
    manufacturer, category = references(browser)
    item = serialized_item(browser, manufacturer, category, "MONITOR-03")
    detail = browser.get("/api/v1/inventory/items/" + item["id"]).json()
    assert detail["is_low_stock"] is False
    assert browser.get("/api/v1/inventory/items", params={"low_stock": "true"}).json()["total"] == 0
    receipt = browser.post(
        "/api/v1/inventory/receipts",
        headers={**headers(browser), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "document_date": "2026-10-23",
            "items": [{"inventory_item_id": item["id"], "quantity": 1}],
        },
    )
    assert receipt.status_code == 409
    assert receipt.json()["detail"]["code"] == "serialized_item_requires_instance_document"


def test_dashboard_reports_current_equipment_state(catalog):
    browser, _ = catalog
    manufacturer, category = references(browser)
    item = serialized_item(browser, manufacturer, category, "MONITOR-METRICS")
    create(browser, "equipment/instances", {"inventory_item_id": item["id"]})
    create(
        browser,
        "equipment/instances",
        {"inventory_item_id": item["id"], "current_recipient": "Иванов И.И."},
    )
    create(
        browser,
        "equipment/instances",
        {"inventory_item_id": item["id"], "is_under_repair": True},
    )
    metrics = {row["key"]: row for row in browser.get("/api/v1/dashboard").json()["metrics"]}
    assert metrics["equipment_total"] == {
        "key": "equipment_total",
        "label": "Всего оборудования",
        "value": 3,
        "available": True,
    }
    assert metrics["equipment_stock"]["value"] == 1
    assert metrics["equipment_active"]["value"] == 1
    assert metrics["equipment_maintenance"]["value"] == 1


def test_transfer_document_replay_contains_equipment_and_cancel_is_rejected(catalog):
    browser, _ = catalog
    manufacturer, category = references(browser)
    item = serialized_item(browser, manufacturer, category, "MONITOR-TRANSFER")
    instance = create(
        browser,
        "equipment/instances",
        {"inventory_item_id": item["id"], "current_building": "Корпус А", "current_room": "101"},
    )
    transfer_key = uuid.uuid4()
    transfer_payload = {
        "document_date": "2026-10-24",
        "destination_building": "Корпус Б",
        "destination_room": "202",
        "items": [
            {
                "equipment_instance_id": instance["id"],
                "version": instance["version"],
                "current_building": instance["current_building"],
                "current_room": instance["current_room"],
                "current_department": instance["current_department"],
                "current_recipient": instance["current_recipient"],
            }
        ],
    }
    transfer = browser.post(
        "/api/v1/equipment/movements",
        headers={**headers(browser), "Idempotency-Key": str(transfer_key)},
        json=transfer_payload,
    )
    assert transfer.status_code == 201, transfer.text
    document_id = transfer.json()["id"]
    fetched = browser.get(f"/api/v1/inventory/documents/{document_id}")
    assert fetched.status_code == 200
    assert fetched.json()["equipment_items"][0]["equipment_instance_id"] == instance["id"]

    replay = browser.post(
        "/api/v1/equipment/movements",
        headers={**headers(browser), "Idempotency-Key": str(transfer_key)},
        json=transfer_payload,
    )
    assert replay.status_code == 200
    assert replay.json()["equipment_items"] == fetched.json()["equipment_items"]
    assert (
        browser.get("/api/v1/inventory/documents", params={"document_type": "transfer"}).json()[
            "total"
        ]
        == 1
    )

    cancel = browser.post(
        f"/api/v1/inventory/documents/{document_id}/cancel",
        headers={**headers(browser), "Idempotency-Key": str(uuid.uuid4())},
        json={"reason": "Проверка запрета отмены перемещения"},
    )
    assert cancel.status_code == 409
    assert cancel.json()["detail"]["code"] == "transfer_cancel_not_supported"
    assert (
        browser.get("/api/v1/inventory/documents", params={"document_type": "reversal"}).json()[
            "total"
        ]
        == 0
    )
    current = browser.get(
        "/api/v1/equipment/instances", params={"inventory_item_id": item["id"]}
    ).json()
    assert current["total"] == 1
    assert current["items"][0]["current_room"] == "202"
    assert current["items"][0]["current_building"] == "Корпус Б"
    assert current["items"][0]["version"] == 2
    history = browser.get(
        "/api/v1/equipment/movements", params={"instance_id": instance["id"]}
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
