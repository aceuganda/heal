"""three_tier_user_roles

Renames the MEMBER tier from its old name and leaves ADMIN alone.

Roles become SUPER_ADMIN / ADMIN / MEMBER. Only the rename needs data work:
rows written before the split hold 'BASIC', which the new enum still accepts on
read purely so a deployment does not 500 on every login in the window between
the code shipping and this migration running. Converting them here closes that
window; `UserRole.BASIC` can be deleted once every environment is past this
revision.

The column is a VARCHAR (Enum(..., native_enum=False)), so there is no Postgres
enum type to ALTER. There is, however, a LENGTH: SQLAlchemy sized it to the
longest name it knew, and 'BASIC' and 'ADMIN' are both 5 characters. 'MEMBER'
is 6 and 'SUPER_ADMIN' is 11, so the column is widened before any row is
rewritten -- otherwise the UPDATE fails with StringDataRightTruncationError and
the whole migration rolls back. 11 matches what the model now generates.

SQLAlchemy persists the enum NAME, hence 'BASIC' rather than 'basic'.

No table is dropped and no row is deleted.

Revision ID: a1c4f7d2e9b0
Revises: 853cc4ff26b5
Create Date: 2026-08-31 18:20:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c4f7d2e9b0"
down_revision = "853cc4ff26b5"
branch_labels = None
depends_on = None

# Longest role name: SUPER_ADMIN.
ROLE_LENGTH = 11
# Longest name before the split: BASIC and ADMIN.
PREVIOUS_ROLE_LENGTH = 5


def upgrade() -> None:
    # Widen first: 'MEMBER' does not fit in the old varchar(5).
    op.alter_column(
        "user",
        "role",
        existing_type=sa.String(length=PREVIOUS_ROLE_LENGTH),
        type_=sa.String(length=ROLE_LENGTH),
        existing_nullable=False,
    )
    op.execute("UPDATE \"user\" SET role = 'MEMBER' WHERE role = 'BASIC'")


def downgrade() -> None:
    # Convert before narrowing, or the rows that no longer fit block the ALTER.
    #
    # SUPER_ADMIN has no pre-split equivalent; the closest true statement is
    # that they were admins, so they go back to ADMIN rather than being
    # silently demoted to a member and losing their access.
    op.execute("UPDATE \"user\" SET role = 'ADMIN' WHERE role = 'SUPER_ADMIN'")
    op.execute("UPDATE \"user\" SET role = 'BASIC' WHERE role = 'MEMBER'")
    op.alter_column(
        "user",
        "role",
        existing_type=sa.String(length=ROLE_LENGTH),
        type_=sa.String(length=PREVIOUS_ROLE_LENGTH),
        existing_nullable=False,
    )
