from contextlib import asynccontextmanager

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import PROJECT_ROOT, Settings
from app.db.session import build_engine
from app.modules.dashboard.router import router as dashboard_router
from app.modules.directory.router import router as directory_router
from app.modules.equipment.router import router as equipment_router
from app.modules.files.middleware import PhotoBodyLimitMiddleware
from app.modules.files.router import router as files_router
from app.modules.health.router import router as health_router
from app.modules.identity.router import router as identity_router
from app.modules.inventory.draft_router import router as draft_router
from app.modules.inventory.export_router import router as export_router
from app.modules.inventory.router import router as inventory_router
from app.modules.inventory.stock_router import router as stock_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        app.state.migration_heads = set(ScriptDirectory.from_config(config).get_heads())
        app.state.engine = build_engine(settings)
        app.state.settings = settings
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(
        title="ИТ-элемент [29]",
        version="0.1.0",
        lifespan=lifespan,
        redirect_slashes=False,
        docs_url="/docs" if settings.enable_api_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_api_docs else None,
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(identity_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(stock_router, prefix="/api/v1")
    app.include_router(equipment_router, prefix="/api/v1")
    app.include_router(inventory_router, prefix="/api/v1")
    app.include_router(export_router, prefix="/api/v1")
    app.include_router(draft_router, prefix="/api/v1")
    app.include_router(directory_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.add_middleware(PhotoBodyLimitMiddleware, max_body_bytes=settings.photo_max_bytes + 65536)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Default validation errors echo `input`, which can include plaintext passwords.
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "validation_error",
                    "message": "Проверьте заполнение полей и требования к паролю.",
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        code = getattr(getattr(exc, "orig", None), "sqlstate", None)
        busy = code in {"55P03", "57014", "40P01", "40001"}
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "operation_busy" if busy else "database_unavailable",
                    "message": (
                        "Операция занята. Повторите запрос с тем же ключом."
                        if busy
                        else "Сервис временно недоступен. Повторите позже."
                    ),
                }
            },
        )

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app
