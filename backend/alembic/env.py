import asyncio
from logging.config import fileConfig

from alembic import context
from danswer.db.engine import build_connection_string
from danswer.db.models import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from celery.backends.database.session import ResultModelBase  # type: ignore

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = [Base.metadata, ResultModelBase.metadata]

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = build_connection_string()
    context.configure(
        url=url,
        target_metadata=target_metadata,  # type: ignore
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)  # type: ignore

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """

    print("Building async engine...")
    connection_string = build_connection_string()
    print(f"Using connection string: {connection_string}")

    connectable = create_async_engine(
        connection_string,
        poolclass=pool.NullPool,
    )

    try:
        print("Connecting to the database...")
        async with connectable.connect() as connection:
            print("Connection established.")
            print("Running migrations...")
            await connection.run_sync(do_run_migrations)
            print("Migrations completed.")
    except Exception as e:
        print(f"Error during migration: {e}")
        raise
    finally:
        print("Disposing engine...")
        await connectable.dispose()
        print("Engine disposed.")



def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
