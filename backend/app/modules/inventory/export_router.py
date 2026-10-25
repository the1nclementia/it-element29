import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.modules.identity.dependencies import Database, require_permission
from app.modules.identity.models import User
from app.modules.inventory.export_service import export_balances, export_movements

router = APIRouter(prefix="/inventory/exports", tags=["Экспорт склада"])
Reader = Annotated[User, Depends(require_permission("inventory.read"))]


def download(content: bytes, filename: str) -> Response:
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/balances.xlsx")
def balances(
    session: Database,
    user: Reader,
    q: str = Query(default="", max_length=100),
    category_id: uuid.UUID | None = None,
    manufacturer_id: uuid.UUID | None = None,
    printer_model_id: uuid.UUID | None = None,
    in_stock: bool | None = None,
    low_stock: bool | None = None,
    archived: Literal["false", "true", "all"] = "false",
    sort: Literal["code", "model", "balance"] = "code",
    direction: Literal["asc", "desc"] = "asc",
):
    return download(
        export_balances(
            session,
            q=q,
            category_id=category_id,
            manufacturer_id=manufacturer_id,
            printer_model_id=printer_model_id,
            in_stock=in_stock,
            low_stock=low_stock,
            archived=archived,
            sort=sort,
            direction=direction,
        ),
        "balances.xlsx",
    )


@router.get("/movements.xlsx")
def movements(
    session: Database,
    user: Reader,
    item_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    document_type: Literal["receipt", "issue", "reversal", "return", "replacement", "transfer"]
    | None = None,
    recipient_employee_id: uuid.UUID | None = None,
):
    return download(
        export_movements(
            session,
            item_id=item_id,
            date_from=date_from,
            date_to=date_to,
            document_type=document_type,
            recipient_employee_id=recipient_employee_id,
        ),
        "movements.xlsx",
    )
