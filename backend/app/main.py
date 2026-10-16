from contextlib import asynccontextmanager

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI

from app.core.config import PROJECT_ROOT, Settings
from app.db.session import build_engine
from app.modules.health.router import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        app.state.migration_heads = set(ScriptDirectory.from_config(config).get_heads())
        app.state.engine = build_engine(settings)
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(
        title="ИТ-элемент [29]",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_api_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_api_docs else None,
    )
    app.include_router(health_router, prefix="/api/v1")
    return app
