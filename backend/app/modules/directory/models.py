import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordMixin


class Department(RecordMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint("length(btrim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
    )

    version: Mapped[int] = mapped_column(default=1, server_default="1")
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Employee(RecordMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("length(btrim(personnel_number)) > 0", name="number_not_blank"),
        CheckConstraint("length(btrim(full_name)) > 0", name="name_not_blank"),
    )

    version: Mapped[int] = mapped_column(default=1, server_default="1")
    personnel_number: Mapped[str] = mapped_column(String(50), unique=True)
    full_name: Mapped[str] = mapped_column(String(300))
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        index=True,
    )


class Location(RecordMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("length(btrim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
    )

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        index=True,
    )
