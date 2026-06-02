from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_create_rule_registry_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "right_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "accesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("secret_ref", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource_id", "name", name="uq_access_resource_name"),
    )
    op.create_index("ix_accesses_resource_id", "accesses", ["resource_id"])

    op.create_table(
        "right_group_accesses",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["access_id"], ["accesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["right_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "access_id"),
    )

    op.create_table(
        "right_group_conflicts",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conflicting_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "group_id <> conflicting_group_id",
            name="ck_right_group_conflict_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["conflicting_group_id"],
            ["right_groups.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["right_groups.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_id", "conflicting_group_id"),
    )


def downgrade() -> None:

    op.drop_table("right_group_conflicts")
    op.drop_table("right_group_accesses")
    op.drop_index("ix_accesses_resource_id", table_name="accesses")
    op.drop_table("accesses")
    op.drop_table("right_groups")
    op.drop_table("resources")
