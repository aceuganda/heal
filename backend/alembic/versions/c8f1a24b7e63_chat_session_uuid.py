"""chat session id becomes a uuid

The session id is the one identifier that reaches a URL (`/chat?chatId=...`).
A sequential one tells anybody who sees it how much the deployment is being
used, and lets them probe for sessions that exist. It matters most where auth
is disabled: ownership is then `user_id IS NULL` for everyone, so a guessable
id is the only thing between one anonymous visitor and another's conversation.

Message ids stay sequential. They never appear in a URL and are only reached
through a session whose ownership has already been checked.

**Existing rows keep their conversations.** New UUIDs are minted per session and
carried into `chat_message.chat_session_id` through a join on the old integer,
so no message is orphaned. The old integer is NOT preserved in a second column:
a stale sequential id left lying around is the thing this migration exists to
remove, and anything still reading it should fail loudly here rather than
quietly keep working.

**This is not reversible without data loss.** The downgrade re-numbers sessions
from a fresh sequence, so any URL, bookmark or external reference to a UUID is
dead afterwards. It exists to unblock a local rollback, not to be run against
data anybody cares about.

Revision ID: c8f1a24b7e63
Revises: b7e3c9a41d52
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c8f1a24b7e63"
down_revision = "b7e3c9a41d52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgcrypto rather than gen_random_uuid() unqualified: the built-in arrived
    # in PostgreSQL 13, and the deployment target is not pinned above that.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.add_column(
        "chat_session",
        sa.Column("new_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE chat_session SET new_id = gen_random_uuid()")
    op.alter_column("chat_session", "new_id", nullable=False)

    op.add_column(
        "chat_message",
        sa.Column("new_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE chat_message
        SET new_session_id = chat_session.new_id
        FROM chat_session
        WHERE chat_message.chat_session_id = chat_session.id
        """
    )

    # A message whose session vanished cannot be shown to anybody and would
    # block the NOT NULL below. Deleting is safe: the session row it belonged
    # to is already gone.
    op.execute("DELETE FROM chat_message WHERE new_session_id IS NULL")
    op.alter_column("chat_message", "new_session_id", nullable=False)

    op.drop_constraint(
        "chat_message_chat_session_id_fkey", "chat_message", type_="foreignkey"
    )
    op.drop_column("chat_message", "chat_session_id")
    op.alter_column("chat_message", "new_session_id", new_column_name="chat_session_id")

    op.drop_constraint("chat_session_pkey", "chat_session", type_="primary")
    op.drop_column("chat_session", "id")
    op.alter_column("chat_session", "new_id", new_column_name="id")
    op.create_primary_key("chat_session_pkey", "chat_session", ["id"])

    op.create_foreign_key(
        "chat_message_chat_session_id_fkey",
        "chat_message",
        "chat_session",
        ["chat_session_id"],
        ["id"],
    )
    # Every read of a conversation filters on this; without an index the UUID
    # column is a sequential scan where the integer had the primary key.
    op.create_index(
        "ix_chat_message_chat_session_id", "chat_message", ["chat_session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_chat_message_chat_session_id", table_name="chat_message")
    op.drop_constraint(
        "chat_message_chat_session_id_fkey", "chat_message", type_="foreignkey"
    )

    op.add_column("chat_session", sa.Column("old_id", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY time_created) AS n
            FROM chat_session
        )
        UPDATE chat_session SET old_id = numbered.n
        FROM numbered WHERE chat_session.id = numbered.id
        """
    )

    op.add_column(
        "chat_message", sa.Column("old_session_id", sa.Integer(), nullable=True)
    )
    op.execute(
        """
        UPDATE chat_message
        SET old_session_id = chat_session.old_id
        FROM chat_session
        WHERE chat_message.chat_session_id = chat_session.id
        """
    )
    op.execute("DELETE FROM chat_message WHERE old_session_id IS NULL")

    op.drop_column("chat_message", "chat_session_id")
    op.alter_column("chat_message", "old_session_id", new_column_name="chat_session_id")
    op.alter_column("chat_message", "chat_session_id", nullable=False)

    op.drop_constraint("chat_session_pkey", "chat_session", type_="primary")
    op.drop_column("chat_session", "id")
    op.alter_column("chat_session", "old_id", new_column_name="id")
    op.alter_column("chat_session", "id", nullable=False)
    op.create_primary_key("chat_session_pkey", "chat_session", ["id"])

    op.execute(
        """
        CREATE SEQUENCE IF NOT EXISTS chat_session_id_seq OWNED BY chat_session.id
        """
    )
    op.execute(
        """
        SELECT setval(
            'chat_session_id_seq',
            COALESCE((SELECT MAX(id) FROM chat_session), 0) + 1,
            false
        )
        """
    )
    op.execute(
        "ALTER TABLE chat_session ALTER COLUMN id "
        "SET DEFAULT nextval('chat_session_id_seq')"
    )

    op.create_foreign_key(
        "chat_message_chat_session_id_fkey",
        "chat_message",
        "chat_session",
        ["chat_session_id"],
        ["id"],
    )
