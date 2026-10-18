from alembic import context

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
from app.modules.directory import models  # noqa: F401
from app.modules.files import models as files_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401

target_metadata = Base.metadata


def migration_settings() -> Settings:
    # Embedded callers pass the same validated settings as their engine.
    # In particular, destructive tests must not reload a different local .env.
    return context.config.attributes.get("settings") or Settings()


def run_migrations_offline() -> None:
    context.configure(
        url=migration_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = build_engine(migration_settings())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
