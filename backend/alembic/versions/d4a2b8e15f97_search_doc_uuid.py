"""search doc id becomes a uuid

`search_doc.id` reaches the browser in a message's citation map and is taken
straight off the URL by `GET /chat/reference/{search_doc_id}/gloss`. That
handler authenticates the caller but does not check the row belongs to them, so
a sequential id could be walked to read every cited guideline passage in the
deployment. A UUID removes the enumeration; it does not make the handler check
ownership, which remains open by decision.

**Citation maps on existing messages are cleared, not rewritten.** They hold
integer ids that no longer resolve. Rewriting them meant a correlated join
through `jsonb_each_text`, which fails outright on any row whose `citations` is
a JSON scalar or `null` rather than an object -- and real rows are. Clearing is
one statement that cannot fail on malformed JSON, and the cost is that markers
in old answers render as plain text, which is exactly what the UI already does
with a citation it cannot resolve.

Revision ID: d4a2b8e15f97
Revises: c8f1a24b7e63
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4a2b8e15f97"
down_revision = "c8f1a24b7e63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Old citation maps point at integers that are about to stop existing.
    op.execute("UPDATE chat_message SET citations = NULL")

    op.add_column(
        "search_doc",
        sa.Column("new_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE search_doc SET new_id = gen_random_uuid()")
    op.alter_column("search_doc", "new_id", nullable=False)

    op.add_column(
        "chat_message__search_doc",
        sa.Column("new_search_doc_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE chat_message__search_doc link
        SET new_search_doc_id = search_doc.new_id
        FROM search_doc
        WHERE link.search_doc_id = search_doc.id
        """
    )
    op.execute("DELETE FROM chat_message__search_doc WHERE new_search_doc_id IS NULL")
    op.alter_column("chat_message__search_doc", "new_search_doc_id", nullable=False)

    op.drop_constraint(
        "chat_message__search_doc_search_doc_id_fkey",
        "chat_message__search_doc",
        type_="foreignkey",
    )
    op.drop_constraint(
        "chat_message__search_doc_pkey", "chat_message__search_doc", type_="primary"
    )
    op.drop_column("chat_message__search_doc", "search_doc_id")
    op.alter_column(
        "chat_message__search_doc",
        "new_search_doc_id",
        new_column_name="search_doc_id",
    )
    op.create_primary_key(
        "chat_message__search_doc_pkey",
        "chat_message__search_doc",
        ["chat_message_id", "search_doc_id"],
    )

    op.drop_constraint("search_doc_pkey", "search_doc", type_="primary")
    op.drop_column("search_doc", "id")
    op.alter_column("search_doc", "new_id", new_column_name="id")
    op.create_primary_key("search_doc_pkey", "search_doc", ["id"])

    op.create_foreign_key(
        "chat_message__search_doc_search_doc_id_fkey",
        "chat_message__search_doc",
        "search_doc",
        ["search_doc_id"],
        ["id"],
    )


def downgrade() -> None:
    """Re-numbers rows from a fresh sequence. Citation maps are cleared again."""
    op.drop_constraint(
        "chat_message__search_doc_search_doc_id_fkey",
        "chat_message__search_doc",
        type_="foreignkey",
    )
    op.execute("UPDATE chat_message SET citations = NULL")

    op.add_column("search_doc", sa.Column("old_id", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS n FROM search_doc
        )
        UPDATE search_doc SET old_id = numbered.n
        FROM numbered WHERE search_doc.id = numbered.id
        """
    )

    op.add_column(
        "chat_message__search_doc",
        sa.Column("old_search_doc_id", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE chat_message__search_doc link
        SET old_search_doc_id = search_doc.old_id
        FROM search_doc
        WHERE link.search_doc_id = search_doc.id
        """
    )
    op.execute("DELETE FROM chat_message__search_doc WHERE old_search_doc_id IS NULL")

    op.drop_constraint(
        "chat_message__search_doc_pkey", "chat_message__search_doc", type_="primary"
    )
    op.drop_column("chat_message__search_doc", "search_doc_id")
    op.alter_column(
        "chat_message__search_doc",
        "old_search_doc_id",
        new_column_name="search_doc_id",
    )
    op.alter_column("chat_message__search_doc", "search_doc_id", nullable=False)
    op.create_primary_key(
        "chat_message__search_doc_pkey",
        "chat_message__search_doc",
        ["chat_message_id", "search_doc_id"],
    )

    op.drop_constraint("search_doc_pkey", "search_doc", type_="primary")
    op.drop_column("search_doc", "id")
    op.alter_column("search_doc", "old_id", new_column_name="id")
    op.alter_column("search_doc", "id", nullable=False)
    op.create_primary_key("search_doc_pkey", "search_doc", ["id"])

    op.execute("CREATE SEQUENCE IF NOT EXISTS search_doc_id_seq OWNED BY search_doc.id")
    op.execute(
        """
        SELECT setval(
            'search_doc_id_seq',
            COALESCE((SELECT MAX(id) FROM search_doc), 0) + 1,
            false
        )
        """
    )
    op.execute(
        "ALTER TABLE search_doc ALTER COLUMN id "
        "SET DEFAULT nextval('search_doc_id_seq')"
    )

    op.create_foreign_key(
        "chat_message__search_doc_search_doc_id_fkey",
        "chat_message__search_doc",
        "search_doc",
        ["search_doc_id"],
        ["id"],
    )
