import uuid

import pytest
from pydantic import ValidationError

from app.modules.inventory.schemas import CategoryCreate, ItemCreate
from app.modules.inventory.stock_schemas import IssueInput
from app.modules.inventory.stock_service import request_hash


def issue_payload(**values):
    return {
        "document_date": "2026-10-22",
        "items": [{"inventory_item_id": str(uuid.uuid4()), "quantity": 1}],
        **values,
    }


def test_catalog_codes_are_optional_for_server_generation():
    category = CategoryCreate.model_validate({"name": "Мониторы"})
    item = ItemCreate.model_validate(
        {
            "category_id": uuid.uuid4(),
            "manufacturer_id": uuid.uuid4(),
            "model": "P2422H",
        }
    )
    assert category.name == "Мониторы"
    assert item.model == "P2422H"


def test_issue_accepts_manual_recipient_without_employee():
    payload = issue_payload(
        recipient_name="Иван Петров",
        recipient_building="Корпус А",
        recipient_room="305",
        recipient_department="ИТ",
    )
    issue = IssueInput.model_validate(payload)
    assert issue.recipient_employee_id is None
    assert issue.recipient_name == "Иван Петров"
    assert issue.recipient_building == "Корпус А"


def test_issue_requires_employee_or_manual_recipient_name():
    with pytest.raises(ValidationError):
        IssueInput.model_validate(issue_payload())


def test_old_employee_issue_payload_remains_valid():
    issue = IssueInput.model_validate(issue_payload(recipient_employee_id=str(uuid.uuid4())))
    assert issue.recipient_name is None


def test_manual_recipient_fields_are_trimmed_and_bounded_in_drafts():
    from app.modules.inventory.draft_schemas import IssueDraftPayload

    value = {
        "recipient_name": "  Иван Петров  ",
        "recipient_building": " Корпус А ",
        "recipient_room": " 305 ",
    }
    draft = IssueDraftPayload.model_validate(value)
    assert draft.recipient_name == "Иван Петров"
    assert draft.recipient_building == "Корпус А"
    assert draft.recipient_room == "305"


def test_new_optional_recipient_fields_preserve_historical_idempotency_hash():
    old = {
        "document_date": "2026-10-22",
        "comment": "",
        "items": [{"inventory_item_id": str(uuid.uuid4()), "quantity": 1}],
        "recipient_employee_id": str(uuid.uuid4()),
        "recipient_room": None,
    }
    new = {
        **old,
        "recipient_name": None,
        "recipient_building": None,
        "recipient_department": None,
    }
    assert request_hash(old) == request_hash(new)
    assert request_hash({**new, "recipient_building": "Корпус А"}) != request_hash(old)
