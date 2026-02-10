"""init schema

Revision ID: 0001_init_schema
Revises:
Create Date: 2026-02-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_init_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("login", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admins_login", "admins", ["login"], unique=True)

    op.create_table(
        "classes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("letter", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        sa.Column("total_points", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("grade >= 5 AND grade <= 11", name="ck_classes_grade_range"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_classes_name", "classes", ["name"], unique=True)

    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fcm_token", sa.String(length=1024), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_devices_fcm_token", "devices", ["fcm_token"], unique=True)

    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("datetime_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("banner_image_url", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_admin_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admins.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_datetime_start", "events", ["datetime_start"], unique=False)
    op.create_index("ix_events_status", "events", ["status"], unique=False)

    op.create_table(
        "event_blocks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("text", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_blocks_event_id", "event_blocks", ["event_id"], unique=False)
    op.create_index("ix_event_blocks_event_sort_order", "event_blocks", ["event_id", "sort_order"], unique=False)

    op.create_table(
        "point_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("delta_points", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_admin_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admins.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_point_transactions_class_id", "point_transactions", ["class_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_point_transactions_class_id", table_name="point_transactions")
    op.drop_table("point_transactions")

    op.drop_index("ix_event_blocks_event_sort_order", table_name="event_blocks")
    op.drop_index("ix_event_blocks_event_id", table_name="event_blocks")
    op.drop_table("event_blocks")

    op.drop_index("ix_events_status", table_name="events")
    op.drop_index("ix_events_datetime_start", table_name="events")
    op.drop_table("events")

    op.drop_index("ix_devices_fcm_token", table_name="devices")
    op.drop_table("devices")

    op.drop_index("ix_classes_name", table_name="classes")
    op.drop_table("classes")

    op.drop_index("ix_admins_login", table_name="admins")
    op.drop_table("admins")

