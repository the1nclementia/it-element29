import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class StockInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)


class DocumentLineInput(StockInput):
    inventory_item_id: uuid.UUID
    quantity: Annotated[StrictInt, Field(ge=1, le=1_000_000)]


class DocumentInput(StockInput):
    document_date: date
    comment: str = Field(default="", max_length=2000)
    items: list[DocumentLineInput] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def unique_items(cls, values):
        if len({line.inventory_item_id for line in values}) != len(values):
            raise ValueError("Позиция не может повторяться в одном документе.")
        return values


class ReceiptInput(DocumentInput):
    receipt_purpose: Literal["delivery", "opening_balance"] = "delivery"
    external_number: str | None = Field(default=None, max_length=100)
    supplier_name: str | None = Field(default=None, max_length=200)


class IssueInput(DocumentInput):
    recipient_employee_id: uuid.UUID
    recipient_room: str | None = Field(default=None, max_length=100)


class ReversalInput(StockInput):
    reason: str = Field(min_length=1, max_length=1000)
