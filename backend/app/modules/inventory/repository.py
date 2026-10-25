import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.modules.inventory.models import InventoryMovement


def is_low_stock(balance: int, minimum: int) -> bool:
    """Return the shared attention rule for a current stock balance."""
    return (minimum > 0 and balance <= minimum) or (minimum == 0 and balance == 0)


def low_stock_expression(balance, minimum):
    """Build the SQL expression matching :func:`is_low_stock`."""
    return or_(and_(minimum > 0, balance <= minimum), and_(minimum == 0, balance == 0))


def balances(session: Session, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not item_ids:
        return {}
    rows = session.execute(
        select(InventoryMovement.inventory_item_id, func.sum(InventoryMovement.delta))
        .where(InventoryMovement.inventory_item_id.in_(item_ids))
        .group_by(InventoryMovement.inventory_item_id)
    )
    return {item_id: int(amount) for item_id, amount in rows}


def get_balance(session: Session, item_id: uuid.UUID) -> int:
    return balances(session, [item_id]).get(item_id, 0)


def balance_query():
    return (
        select(
            InventoryMovement.inventory_item_id.label("item_id"),
            func.sum(InventoryMovement.delta).label("balance"),
        )
        .group_by(InventoryMovement.inventory_item_id)
        .subquery()
    )


def escaped_like(query: str) -> str:
    return "%" + query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def archived_filter(statement, model, archived: str):
    if archived == "false":
        return statement.where(model.archived_at.is_(None))
    if archived == "true":
        return statement.where(model.archived_at.is_not(None))
    return statement
