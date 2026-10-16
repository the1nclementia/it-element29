"""Initial directories. No business operations or authentication in stage 1."""

import sqlalchemy as sa
from alembic import op

revision = "0001_directories"
down_revision = None
branch_labels = None
depends_on = None


def record_columns():
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "departments",
        *record_columns(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
        sa.UniqueConstraint("code", name="uq_departments_code"),
        sa.CheckConstraint("length(btrim(code)) > 0", name=op.f("ck_departments_code_not_blank")),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_departments_name_not_blank")),
    )
    op.create_table(
        "employees",
        *record_columns(),
        sa.Column("personnel_number", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(300), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_employees"),
        sa.UniqueConstraint("personnel_number", name="uq_employees_personnel_number"),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_employees_department_id_departments",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(btrim(personnel_number)) > 0",
            name=op.f("ck_employees_number_not_blank"),
        ),
        sa.CheckConstraint(
            "length(btrim(full_name)) > 0", name=op.f("ck_employees_name_not_blank")
        ),
    )
    op.create_index("ix_employees_department_id", "employees", ["department_id"])
    op.create_table(
        "locations",
        *record_columns(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_locations"),
        sa.UniqueConstraint("code", name="uq_locations_code"),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_locations_department_id_departments",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(btrim(code)) > 0", name=op.f("ck_locations_code_not_blank")),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_locations_name_not_blank")),
    )
    op.create_index("ix_locations_department_id", "locations", ["department_id"])


def downgrade() -> None:
    op.drop_table("locations")
    op.drop_table("employees")
    op.drop_table("departments")
