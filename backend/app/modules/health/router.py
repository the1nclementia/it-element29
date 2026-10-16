from typing import Literal

from alembic.runtime.migration import MigrationContext
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/health", tags=["Состояние сервера"])


class HealthResponse(BaseModel):
    status: Literal["ok", "not_ready"]


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def ready(request: Request, response: Response) -> HealthResponse:
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            applied = set(MigrationContext.configure(connection).get_current_heads())
            if applied == request.app.state.migration_heads:
                return HealthResponse(status="ok")
    except SQLAlchemyError:
        # Driver exceptions can contain DSNs/SQL. Do not expose or log their text.
        pass
    response.status_code = 503
    return HealthResponse(status="not_ready")
