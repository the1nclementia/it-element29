import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin


class Role(Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permissions.code", ondelete="RESTRICT"),
        primary_key=True,
    )


class User(RecordMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username = lower(username)", name="username_normalized"),
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_not_blank"),
    )
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(Text)
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)


class AuthSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (CheckConstraint("attempts > 0", name="positive_attempts"),)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[uuid.UUID | None]
    changes: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
