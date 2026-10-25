"""Test-harness-only Alembic environment.

Never reads the application's production DATABASE_URL. Requires explicit
A04_TEST_POSTGRES_URL and only operates on a disposable test database.
"""
import os
from alembic import context
from sqlalchemy import create_engine, pool
from app.db import Base

config=context.config
target_metadata=Base.metadata

def run_migrations_online():
    url=os.environ.get("A04_TEST_POSTGRES_URL")
    if not url or "localhost" not in url and "127.0.0.1" not in url:
        raise RuntimeError("TEST_DATABASE_URL_REQUIRED")
    engine=create_engine(url,poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection,target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()

if context.is_offline_mode():
    raise RuntimeError("OFFLINE_MIGRATIONS_DISABLED")
run_migrations_online()
