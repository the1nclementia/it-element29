from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=3,
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.db_connect_timeout,
            "options": "-c timezone=UTC -c statement_timeout=3000",
        },
    )


def get_session(request: Request) -> Iterator[Session]:
    """Services explicitly commit; closing rolls back unfinished work."""
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session
