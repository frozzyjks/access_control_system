from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0002_add_access_requests"
down_revision: str | None = "0001_create_rule_registry_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "access_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),

        # Идентификатор пользователя. Авторизации нет, поэтому просто строка
        # (email, username, sub из JWT — решает фронтенд).
        sa.Column("user_id", sa.String(length=255), nullable=False),

        # GRANT или REVOKE — что хочет сделать пользователь.
        sa.Column("operation", sa.String(length=32), nullable=False),

        # ACCESS или RIGHT_GROUP — тип сущности, к которой запрашивается доступ.
        sa.Column("target_type", sa.String(length=32), nullable=False),

        # UUID конкретного Access или RightGroup.
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),

        # PENDING → APPROVED | REJECTED
        sa.Column("status", sa.String(length=32), nullable=False),

        # Причина отказа. Заполняется только при REJECTED.
        sa.Column("rejection_reason", sa.String(length=1000), nullable=True),

        # Временные метки жизненного цикла записи.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),

        # Когда Policy Engine последний раз изменил эту запись.
        # NULL пока заявка PENDING и ещё не была обработана.
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),

        # Кто изменил: "policy-engine", "admin" и т.д.
        # NULL пока заявка не обработана.
        sa.Column("last_modified_by", sa.String(length=255), nullable=True),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_access_requests_user_id", "access_requests", ["user_id"])
    op.create_index("ix_access_requests_status", "access_requests", ["status"])

    op.create_table(
        "user_right_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),

        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_modified_by", sa.String(length=255), nullable=True),

        sa.ForeignKeyConstraint(["group_id"], ["right_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_user_right_groups_user_id", "user_right_groups", ["user_id"])
    op.create_index(
        "ix_user_right_groups_user_active",
        "user_right_groups",
        ["user_id", "is_active"],
    )

    op.create_table(
        "user_accesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "access_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),

        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_modified_by", sa.String(length=255), nullable=True),

        sa.ForeignKeyConstraint(["access_id"], ["accesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_user_accesses_user_id", "user_accesses", ["user_id"])
    op.create_index(
        "ix_user_accesses_user_active",
        "user_accesses",
        ["user_id", "is_active"],
    )


def downgrade() -> None:

    op.drop_index("ix_user_accesses_user_active", table_name="user_accesses")
    op.drop_index("ix_user_accesses_user_id", table_name="user_accesses")
    op.drop_table("user_accesses")

    op.drop_index("ix_user_right_groups_user_active", table_name="user_right_groups")
    op.drop_index("ix_user_right_groups_user_id", table_name="user_right_groups")
    op.drop_table("user_right_groups")

    op.drop_index("ix_access_requests_status", table_name="access_requests")
    op.drop_index("ix_access_requests_user_id", table_name="access_requests")
    op.drop_table("access_requests")