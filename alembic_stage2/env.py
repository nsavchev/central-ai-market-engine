"""Explicit offline-by-default Stage 2 Alembic environment (disposable only)."""
import os
from alembic import context
from sqlalchemy import create_engine, pool

config=context.config
def run_migrations_online():
    if os.getenv("STAGE2_DISPOSABLE_DB")!="YES":
        raise RuntimeError("DISPOSABLE_ONLY")
    url=os.getenv("TEST_POSTGRES_URL")
    if not url or not url.startswith("postgresql+psycopg://") or not url.endswith("/test"):
        raise RuntimeError("DISPOSABLE_URL_REQUIRED")
    engine=create_engine(url,poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            if connection.exec_driver_sql("SELECT current_database()").scalar()!="test":
                raise RuntimeError("REFUSE_NON_TEST_DATABASE")
            context.configure(connection=connection,transactional_ddl=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()

if context.is_offline_mode():
    raise RuntimeError("OFFLINE_MIGRATIONS_DISABLED")
run_migrations_online()
