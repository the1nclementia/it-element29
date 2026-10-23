import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session
from test_exports import sheet
from test_stock import post
from test_stock import stock as stock

from app.modules.inventory.models import InventoryItem

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "minimum,quantity,attention", [(5, 6, False), (5, 5, True), (5, 0, True), (0, 0, True)]
)
def test_attention_agrees_in_catalog_detail_dashboard_and_excel(
    stock, minimum, quantity, attention
):
    browser, engine, _, ids = stock
    item_id, archived_id = ids["items"]
    with Session(engine) as session:
        session.get(InventoryItem, uuid.UUID(item_id)).min_stock = minimum
        session.get(InventoryItem, uuid.UUID(archived_id)).archived_at = datetime.now(UTC)
        session.commit()
    if quantity:
        assert post(browser, "receipts", [(item_id, quantity)]).status_code == 201
    detail = browser.get(f"/api/v1/inventory/items/{item_id}").json()
    assert detail["balance"] == quantity
    assert detail["is_low_stock"] is attention
    for low, expected in [(True, int(attention)), (False, int(not attention))]:
        params = {"low_stock": str(low).lower()}
        catalog = browser.get("/api/v1/inventory/items", params=params).json()
        assert catalog["total"] == expected
        assert [row["id"] for row in catalog["items"]] == ([item_id] if expected else [])
        rows = sheet(browser.get("/api/v1/inventory/exports/balances.xlsx", params=params))
        assert len(rows) == expected + 1
        if expected:
            assert rows[1][5:8] == [quantity, minimum, "Да" if attention else "Нет"]
    metrics = browser.get("/api/v1/dashboard").json()["metrics"]
    assert next(metric["value"] for metric in metrics if metric["key"] == "low_stock") == int(
        attention
    )


def test_attention_changes_after_issue_and_replenishment(stock):
    browser, engine, _, ids = stock
    item_id = ids["items"][0]
    with Session(engine) as session:
        session.get(InventoryItem, uuid.UUID(item_id)).min_stock = 5
        session.commit()
    assert post(browser, "receipts", [(item_id, 6)]).status_code == 201
    for quantity, expected in [(1, 5), (5, 0)]:
        assert (
            post(browser, "issues", [(item_id, quantity)], employee=ids["employee"]).status_code
            == 201
        )
        detail = browser.get(f"/api/v1/inventory/items/{item_id}").json()
        assert detail["balance"] == expected
        assert detail["is_low_stock"] is True
    assert post(browser, "receipts", [(item_id, 6)]).status_code == 201
    detail = browser.get(f"/api/v1/inventory/items/{item_id}").json()
    assert detail["balance"] == 6
    assert detail["is_low_stock"] is False
