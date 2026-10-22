"""account profile and access

Three things an account needs that it did not have:

  * A profile the person fills in themselves: organisation, date of birth and
    sex. All nullable: every existing account has none of them yet, and a
    missing value is "not given", not a default.
  * A second verification level. `is_verified` (from fastapi-users) already
    means "clicked the email link"; `admin_verified_at` records that an admin
    has vouched for the account, and `admin_verified_by_id` who did. A
    timestamp rather than a boolean, so the dashboard can say when.
  * `chat_blocked`, an admin's per-account switch that pauses chat for one
    person without touching anyone else.

Plus `access_policy`, one row (id 1) holding the two deployment-wide switches
that block unverified accounts. No row means nothing is blocked, which is the
state every deployment starts in.

Additive only. Nothing existing is dropped, retyped or rewritten: accounts
keep whatever `is_verified` they had.

Revision ID: c5e8a1f3d742
Revises: a7c3e91d5b20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c5e8a1f3d742"
down_revision = "a7c3e91d5b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("organisation", sa.String(), nullable=True))
    op.add_column("user", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("user", sa.Column("sex", sa.String(), nullable=True))
    op.create_check_constraint(
        "user_sex_known",
        "user",
        "sex IS NULL OR sex IN ('female', 'male', 'prefer_not_to_say')",
    )
    op.add_column(
        "user",
        sa.Column("admin_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("admin_verified_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # SET NULL: removing the admin who vouched must not un-verify everyone
    # they verified, only forget who it was.
    op.create_foreign_key(
        "user_admin_verified_by_fk",
        "user",
        "user",
        ["admin_verified_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "user",
        sa.Column(
            "chat_blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "access_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "block_email_unverified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "block_admin_unverified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.CheckConstraint("id = 1", name="access_policy_single_row"),
    )


def downgrade() -> None:
    # Loses the profiles, the admin verifications, the chat blocks and the
    # policy. Every account falls back to "unblocked", a defined state.
    op.drop_table("access_policy")
    op.drop_column("user", "chat_blocked")
    op.drop_constraint("user_admin_verified_by_fk", "user", type_="foreignkey")
    op.drop_column("user", "admin_verified_by_id")
    op.drop_column("user", "admin_verified_at")
    op.drop_constraint("user_sex_known", "user", type_="check")
    op.drop_column("user", "sex")
    op.drop_column("user", "date_of_birth")
    op.drop_column("user", "organisation")
