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


def test_equipment_instance_identifiers_are_scoped_and_optional(catalog):
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
    empty_numbers = create(browser, "equipment/instances", {"inventory_item_id": item["id"]})
    assert empty_numbers["serial_number"] is None
    assert empty_numbers["inventory_number"] is None


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
