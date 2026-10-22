"""model settings

The generation defaults an admin can change from the playground, persisted.

Until now temperature, reply length, top-p and the default chat model existed
only as environment variables, which means changing one is a redeploy and a
restart -- and an admin comparing two temperatures on the playground could
never keep the one that read better. This table is where that decision lands.

Every column is nullable and NULL means "use the environment". The env vars
stay the source of truth; the row only records where someone has decided
otherwise. Clearing a field is therefore a real operation (set it back to
NULL), not a delete of the row, and a deployment can still be re-pointed by
changing its environment without hunting for a saved value overriding it.

One row, id 1, enforced. There is exactly one answer to "what does this
deployment run at", and a table that could hold two would make that question
ambiguous at the moment it matters most. No row at all is the normal state of
a fresh install: everything follows the environment until somebody saves.

The row is deliberately NOT seeded here. Seeding it would freeze today's
environment values into the database, so a later change to HEAL_TEMPERATURE
would silently do nothing.

Revision ID: f3b6d20c47a1
Revises: d4a2b8e15f97
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f3b6d20c47a1"
down_revision = "d4a2b8e15f97"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("top_p", sa.Float(), nullable=True),
        sa.Column("verbosity", sa.String(), nullable=True),
        sa.Column("chat_model", sa.String(), nullable=True),
        sa.Column("classifier_model", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # SET NULL, not CASCADE: removing the admin who last touched the
        # settings must not delete the deployment's configuration with them.
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
        # The ranges are enforced here as well as in the request model. The API
        # is not the only writer -- one psql session is a typo away from a
        # temperature of 40, which would change how every clinical answer is
        # worded with nothing in the trail to say why.
        sa.CheckConstraint("id = 1", name="model_settings_single_row"),
        sa.CheckConstraint(
            "temperature IS NULL OR (temperature >= 0 AND temperature <= 1)",
            name="model_settings_temperature_range",
        ),
        sa.CheckConstraint(
            "max_output_tokens IS NULL OR "
            "(max_output_tokens >= 64 AND max_output_tokens <= 4096)",
            name="model_settings_max_output_tokens_range",
        ),
        sa.CheckConstraint(
            "top_p IS NULL OR (top_p >= 0 AND top_p <= 1)",
            name="model_settings_top_p_range",
        ),
        sa.CheckConstraint(
            "verbosity IS NULL OR verbosity IN ('brief', 'standard', 'detailed')",
            name="model_settings_verbosity_known",
        ),
    )


def downgrade() -> None:
    # Dropping this loses the saved overrides and the deployment falls back to
    # its environment, which is a defined state rather than a broken one.
    op.drop_table("model_settings")
