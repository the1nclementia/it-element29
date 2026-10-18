"""identity"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_identity"
down_revision = "0001_directories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts > 0", name=op.f("ck_auth_rate_limits_positive_attempts")),
        sa.PrimaryKeyConstraint("key_hash", name=op.f("pk_auth_rate_limits")),
    )
    op.create_index(
        op.f("ix_auth_rate_limits_window_start"), "auth_rate_limits", ["window_start"], unique=False
    )
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_permissions")),
    )
    op.create_table(
        "roles",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_roles")),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.String(length=32), nullable=False),
        sa.Column("permission_code", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permissions.code"],
            name=op.f("fk_role_permissions_permission_code_permissions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["roles.code"],
            name=op.f("fk_role_permissions_role_code_roles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("role_code", "permission_code", name=op.f("pk_role_permissions")),
    )
    op.create_table(
        "users",
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role_code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("must_change_password", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0", name=op.f("ck_users_display_name_not_blank")
        ),
        sa.CheckConstraint("username = lower(username)", name=op.f("ck_users_username_normalized")),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["roles.code"],
            name=op.f("fk_users_role_code_roles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_index(op.f("ix_users_role_code"), "users", ["role_code"], unique=False)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_occurred_at"), "audit_logs", ["occurred_at"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    # Frozen seed data: migrations must not import evolving application permissions.
    roles = sa.table("roles", sa.column("code", sa.String), sa.column("name", sa.String))
    permissions = sa.table("permissions", sa.column("code", sa.String))
    links = sa.table(
        "role_permissions",
        sa.column("role_code", sa.String),
        sa.column("permission_code", sa.String),
    )
    names = {
        "administrator": "Администратор",
        "it_specialist": "ИТ-специалист",
        "storekeeper": "Кладовщик",
        "manager": "Руководитель",
    }
    read = {
        "dashboard.read",
        "inventory.read",
        "equipment.read",
        "movements.read",
        "maintenance.read",
        "history.read",
        "statistics.read",
        "reports.read",
        "settings.read",
    }
    all_permissions = read | {
        "inventory.manage",
        "inventory.issue",
        "equipment.manage",
        "movements.manage",
        "maintenance.manage",
        "users.manage",
    }
    mappings = {
        "administrator": all_permissions,
        "manager": read,
        "it_specialist": read
        | {"inventory.issue", "equipment.manage", "movements.manage", "maintenance.manage"},
        "storekeeper": {
            "dashboard.read",
            "inventory.read",
            "inventory.manage",
            "inventory.issue",
            "equipment.read",
            "history.read",
            "settings.read",
        },
    }
    op.bulk_insert(roles, [{"code": code, "name": name} for code, name in names.items()])
    op.bulk_insert(permissions, [{"code": code} for code in sorted(all_permissions)])
    op.bulk_insert(
        links,
        [
            {"role_code": role, "permission_code": code}
            for role, codes in mappings.items()
            for code in sorted(codes)
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_audit_logs_occurred_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_users_role_code"), table_name="users")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_index(op.f("ix_auth_rate_limits_window_start"), table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
