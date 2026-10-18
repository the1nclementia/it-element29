import re

from psycopg import sql
from sqlalchemy import Connection, text


def provision_runtime_role(connection: Connection, role: str, password: str) -> None:
    """Explicit operator action; never called by migrations or API startup."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,62}", role) or len(password) < 24:
        raise ValueError(
            "APP_DB_USER: 3–63 символа a-z/0-9/_; APP_DB_PASSWORD: минимум 24 символа."
        )
    owner, database = connection.execute(text("SELECT current_user, current_database()")).one()
    if role == owner or role.startswith("pg_") or role == "postgres":
        raise ValueError("Runtime роль должна отличаться от владельца БД и системных ролей.")
    existing = connection.execute(
        text(
            "SELECT oid, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = :role"
        ),
        {"role": role},
    ).first()
    if existing:
        inherited = connection.scalar(
            text("SELECT count(*) FROM pg_auth_members WHERE member=:oid"), {"oid": existing.oid}
        )
        owns_objects = connection.scalar(
            text("SELECT count(*) FROM pg_class WHERE relowner=:oid"), {"oid": existing.oid}
        )
        if any(existing[1:]) or inherited or owns_objects:
            raise ValueError(
                "Отказ: существующая роль имеет дополнительные права или владеет объектами."
            )
    driver = connection.connection.driver_connection

    def execute(query):
        # Identifiers and passwords use psycopg quoting. CLI never prints SQL exceptions.
        connection.exec_driver_sql(query.as_string(driver))

    execute(
        sql.SQL(
            "{} ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS PASSWORD {}"
        ).format(
            sql.SQL("ALTER" if existing else "CREATE"), sql.Identifier(role), sql.Literal(password)
        )
    )
    execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(role)
        )
    )
    execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
    execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(sql.Identifier(role)))
    execute(
        sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(sql.Identifier(role))
    )
    for privileges, tables in [
        (
            "SELECT",
            [
                "locations",
                "roles",
                "permissions",
                "role_permissions",
                "alembic_version",
            ],
        ),
        (
            "SELECT, INSERT, UPDATE",
            [
                "users",
                "departments",
                "employees",
                "manufacturers",
                "inventory_categories",
                "printer_models",
                "inventory_items",
                "inventory_compatibilities",
                "inventory_item_attachments",
            ],
        ),
        ("SELECT, INSERT, UPDATE, DELETE", ["sessions", "auth_rate_limits"]),
        (
            "SELECT, INSERT",
            [
                "audit_logs",
                "inventory_documents",
                "inventory_document_items",
                "inventory_movements",
                "file_attachments",
            ],
        ),
    ]:
        execute(
            sql.SQL("GRANT {} ON {} TO {}").format(
                sql.SQL(privileges),
                sql.SQL(", ").join(map(sql.Identifier, tables)),
                sql.Identifier(role),
            )
        )

    execute(
        sql.SQL("GRANT USAGE ON SEQUENCE inventory_document_number_seq TO {}").format(
            sql.Identifier(role)
        )
    )
