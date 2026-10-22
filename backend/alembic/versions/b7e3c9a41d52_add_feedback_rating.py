"""add feedback rating

A four-point rating (1 worst, 4 best) on chat_feedback, replacing the thumbs
pair as the control a health worker sees.

Additive and nullable. `is_positive` is deliberately NOT dropped: every row
written before this migration carries a real judgement in that column, and the
two are read together by the aggregate. Backfilling it into `rating` would be a
guess -- a thumbs-up is somewhere in 3..4 and a thumbs-down somewhere in 1..2,
and inventing which would put fabricated numbers into a clinical review signal.
Old rows keep a null rating and are counted as thumbs.

Revision ID: b7e3c9a41d52
Revises: a1c4f7d2e9b0
"""
import sqlalchemy as sa
from alembic import op

revision = "b7e3c9a41d52"
down_revision = "a1c4f7d2e9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_feedback",
        sa.Column("rating", sa.Integer(), nullable=True),
    )
    # Range enforced in the database as well as in the request model. The API
    # is not the only writer -- a backfill script or a psql session is one
    # typo away from a 40-star review that would skew every aggregate reading
    # it, and a constraint is the only thing that stops that at the source.
    op.create_check_constraint(
        "chat_feedback_rating_range",
        "chat_feedback",
        "rating IS NULL OR (rating >= 1 AND rating <= 4)",
    )


def downgrade() -> None:
    op.drop_constraint("chat_feedback_rating_range", "chat_feedback", type_="check")
    op.drop_column("chat_feedback", "rating")
