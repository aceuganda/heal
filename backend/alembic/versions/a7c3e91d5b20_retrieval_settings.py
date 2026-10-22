"""retrieval settings

The retrieval knobs join the generation ones in `model_settings`, so an admin
can save a score floor or a top-k from the playground instead of editing the
environment and restarting the API.

Same rules as the table they join: every column nullable, NULL means "use the
environment", nothing seeded. Ranges match `heal/knowledge/settings.py` BOUNDS
and are enforced here too, because psql is a writer as well as the API.

Additive only: no column is dropped or retyped on upgrade.

Revision ID: a7c3e91d5b20
Revises: f3b6d20c47a1
"""
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "a7c3e91d5b20"
down_revision = "f3b6d20c47a1"
branch_labels = None
depends_on = None

# (column, type, CHECK expression or None)
_COLUMNS: tuple[tuple[str, sa.types.TypeEngine[Any], str | None], ...] = (
    ("min_retrieval_score", sa.Float(), "{c} >= 0 AND {c} <= 1"),
    ("hybrid_alpha", sa.Float(), "{c} >= 0 AND {c} <= 1"),
    ("hybrid_search", sa.Boolean(), None),
    ("retrieval_top_k", sa.Integer(), "{c} >= 1 AND {c} <= 200"),
    ("context_top_k", sa.Integer(), "{c} >= 1 AND {c} <= 50"),
    ("max_chunks_per_source", sa.Integer(), "{c} >= 1 AND {c} <= 50"),
)


def upgrade() -> None:
    for name, type_, check in _COLUMNS:
        op.add_column("model_settings", sa.Column(name, type_, nullable=True))
        if check:
            op.create_check_constraint(
                f"model_settings_{name}_range",
                "model_settings",
                f"{name} IS NULL OR ({check.format(c=name)})",
            )


def downgrade() -> None:
    # Loses only saved retrieval overrides; the deployment falls back to its
    # environment for them, which is a defined state.
    for name, _, check in reversed(_COLUMNS):
        if check:
            op.drop_constraint(
                f"model_settings_{name}_range", "model_settings", type_="check"
            )
        op.drop_column("model_settings", name)
