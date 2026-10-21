import uuid

import pytest
from pydantic import ValidationError

from app.modules.inventory.draft_schemas import IssueDraftPayload, ReceiptDraftPayload
from app.modules.inventory.stock_schemas import IssueInput, ReceiptInput, ReversalInput


def issue(quantity=1):
    return {
        "recipient_employee_id": str(uuid.uuid4()),
        "document_date": "2026-10-18",
        "items": [{"inventory_item_id": str(uuid.uuid4()), "quantity": quantity}],
    }


@pytest.mark.parametrize("quantity", [0, -1, True, False, 1.5, "2", 1_000_001, float("nan")])
def test_document_rejects_invalid_quantities(quantity):
    with pytest.raises(ValidationError):
        IssueInput.model_validate(issue(quantity))


def test_document_requires_nonempty_unique_bounded_lines():
    value = issue()
    for lines in [
        [],
        value["items"] * 2,
        [{"inventory_item_id": str(uuid.uuid4()), "quantity": 1} for _ in range(101)],
    ]:
        with pytest.raises(ValidationError):
            IssueInput.model_validate({**value, "items": lines})


def test_document_accepts_exact_integer_and_rejects_server_fields():
    value = issue(1_000_000)
    assert IssueInput.model_validate(value).items[0].quantity == 1_000_000
    with pytest.raises(ValidationError):
        IssueInput.model_validate({**value, "created_by_id": str(uuid.uuid4())})


def test_receipt_purpose_and_reversal_reason():
    value = issue()
    del value["recipient_employee_id"]
    assert ReceiptInput.model_validate({**value, "receipt_purpose": "opening_balance"})
    with pytest.raises(ValidationError):
        ReceiptInput.model_validate({**value, "receipt_purpose": "return"})
    with pytest.raises(ValidationError):
        ReversalInput(reason="   ")
    assert ReversalInput(reason="  Ошибочная выдача  ").reason == "Ошибочная выдача"


@pytest.mark.parametrize(
    ("schema", "field", "limit"),
    [
        (ReceiptInput, "supplier_name", 200),
        (IssueInput, "recipient_room", 100),
        (ReceiptDraftPayload, "supplier_name", 200),
        (IssueDraftPayload, "recipient_room", 100),
    ],
)
def test_optional_document_details_are_trimmed_bounded_and_backward_compatible(
    schema, field, limit
):
    value = issue()
    if field == "supplier_name":
        del value["recipient_employee_id"]
    assert getattr(schema.model_validate(value), field) is None
    assert getattr(schema.model_validate({**value, field: None}), field) is None
    assert getattr(schema.model_validate({**value, field: "  Тестовый реквизит  "}), field) == (
        "Тестовый реквизит"
    )
    assert getattr(schema.model_validate({**value, field: "Я" * limit}), field) == "Я" * limit
    for invalid in ["Я" * (limit + 1), 123, True, []]:
        with pytest.raises(ValidationError):
            schema.model_validate({**value, field: invalid})
