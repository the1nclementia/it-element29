import io
import uuid
import xml.etree.ElementTree as ET
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_stock import headers, post, receive
from test_stock import stock as stock

from app.main import create_app
from app.modules.inventory.models import InventoryItem

pytestmark = pytest.mark.integration
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def sheet(response):
    assert response.status_code == 200, response.text[:100] if response.status_code != 200 else ""
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            if name.endswith(".xml"):
                ET.fromstring(archive.read(name))
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    assert root.find("s:autoFilter", NS) is not None
    assert root.find(".//s:pane", NS).get("state") == "frozen"
    assert root.find(".//s:f", NS) is None
    rows = []
    for row in root.findall("s:sheetData/s:row", NS):
        rows.append(
            [
                cell.findtext("s:is/s:t", namespaces=NS)
                if cell.get("t") == "inlineStr"
                else int(cell.findtext("s:v", namespaces=NS))
                for cell in row
            ]
        )
    return rows


def test_balance_export_filters_numeric_cells_and_formula_safety(stock):
    browser, engine, _, ids = stock
    receive(stock, (10, 1))
    with Session(engine) as session:
        item = session.get(InventoryItem, uuid.UUID(ids["items"][0]))
        item.model = '=HYPERLINK("https://invalid.example")'
        item.article = "0000123"
        item.description = "Символы <>& и управляющий \x01"
        session.commit()
    rows = sheet(browser.get("/api/v1/inventory/exports/balances.xlsx"))
    assert len(rows) == 3
    assert rows[0][:3] == ["Код", "Модель", "Артикул"]
    assert rows[1][1].startswith("=HYPERLINK")
    assert rows[1][2] == "0000123"
    assert rows[1][5:8] == [10, 2, "Нет"]
    filtered = sheet(
        browser.get("/api/v1/inventory/exports/balances.xlsx", params={"low_stock": "true"})
    )
    assert len(filtered) == 2 and filtered[1][0] == "STOCK-1"


def test_movement_export_snapshots_filters_and_permissions(stock):
    browser, engine, settings, ids = stock
    receive(stock)
    issued = post(
        browser,
        "issues",
        [(ids["items"][0], 3)],
        employee=ids["employee"],
        recipient_building="Корпус А",
    ).json()
    assert (
        browser.post(
            f"/api/v1/inventory/documents/{issued['id']}/cancel",
            headers=headers(browser),
            json={"reason": "Тест экспорта"},
        ).status_code
        == 201
    )
    with Session(engine) as session:
        session.get(InventoryItem, uuid.UUID(ids["items"][0])).model = "Новая модель"
        session.commit()
    rows = sheet(
        browser.get("/api/v1/inventory/exports/movements.xlsx", params={"item_id": ids["items"][0]})
    )
    assert len(rows) == 4
    assert sum(row[7] for row in rows[1:]) == 10
    assert all(row[5] == "Картридж 0" for row in rows[1:])
    assert all(row[15] == "Корпус А" for row in rows[3:])
    empty = sheet(
        browser.get(
            "/api/v1/inventory/exports/movements.xlsx",
            params={"date_from": "2000-01-01", "date_to": "2000-01-02"},
        )
    )
    assert len(empty) == 1
    assert (
        browser.get(
            "/api/v1/inventory/exports/movements.xlsx",
            params={"date_from": "2026-10-20", "date_to": "2026-10-19"},
        ).status_code
        == 422
    )
    with TestClient(create_app(settings)) as anonymous:
        assert anonymous.get("/api/v1/inventory/exports/balances.xlsx").status_code == 401
        assert anonymous.get("/api/v1/inventory/exports/movements.xlsx").status_code == 401


def test_movement_export_filters_document_type_and_recipient(stock):
    browser, _, _, ids = stock
    receive(stock)
    issued = post(browser, "issues", [(ids["items"][0], 3)], employee=ids["employee"])
    assert issued.status_code == 201
    assert (
        browser.post(
            f"/api/v1/inventory/documents/{issued.json()['id']}/cancel",
            headers=headers(browser),
            json={"reason": "Проверка фильтров отчёта"},
        ).status_code
        == 201
    )
    url = "/api/v1/inventory/exports/movements.xlsx"
    receipts = sheet(browser.get(url, params={"document_type": "receipt"}))
    assert len(receipts) == 3
    assert all(row[1] == "Поступление" for row in receipts[1:])
    issues = sheet(
        browser.get(
            url,
            params={
                "document_type": "issue",
                "recipient_employee_id": ids["employee"],
            },
        )
    )
    assert len(issues) == 2
    assert issues[1][0] == issued.json()["number"] and issues[1][7] == -3
    recipient_movements = sheet(browser.get(url, params={"recipient_employee_id": ids["employee"]}))
    assert [row[1] for row in recipient_movements[1:]] == ["Выдача", "Отмена"]
    assert len(sheet(browser.get(url, params={"recipient_employee_id": str(uuid.uuid4())}))) == 1
    assert browser.get(url, params={"document_type": "unknown"}).status_code == 422
