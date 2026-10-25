import importlib.util
from pathlib import Path
import pytest
from alembic.operations import Operations
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
import os

URL=os.getenv("A04_TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL only")

def test_upgrade_downgrade_in_isolated_schema(monkeypatch):
    engine=create_engine(URL)
    path=Path(__file__).resolve().parents[1]/"migrations/versions/a04_shadow_test_01.py"
    spec=importlib.util.spec_from_file_location("a04_test_revision",path)
    revision=importlib.util.module_from_spec(spec);spec.loader.exec_module(revision)
    with engine.begin() as con:
        con.execute(text("DROP SCHEMA IF EXISTS a04_migration_test CASCADE"))
        con.execute(text("CREATE SCHEMA a04_migration_test"))
        con.execute(text("CREATE TABLE a04_migration_test.paper_accounts (id int PRIMARY KEY,cash double precision)"))
        con.execute(text("CREATE TABLE a04_migration_test.paper_trades (id int PRIMARY KEY,quantity double precision,price double precision,fee double precision)"))
        con.execute(text("INSERT INTO a04_migration_test.paper_accounts VALUES (1,100.25)"))
        con.execute(text("INSERT INTO a04_migration_test.paper_trades VALUES (1,2,10.25,0.5)"))
    try:
        with engine.begin() as con:
            ops=Operations(MigrationContext.configure(con))
            monkeypatch.setattr(revision.op,"get_bind",ops.get_bind)
            monkeypatch.setattr(revision.op,"add_column",ops.add_column)
            monkeypatch.setattr(revision.op,"drop_column",ops.drop_column)
            with pytest.raises(RuntimeError,match="DISPOSABLE_MIGRATION_ONLY"):
                revision.upgrade()
            monkeypatch.setenv("A04_DISPOSABLE_MIGRATION","YES")
            monkeypatch.setenv("A04_TEST_SCHEMA","a04_migration_test")
            revision.upgrade()
            names=con.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='a04_migration_test' AND table_name='paper_trades'")).scalars().all()
            assert set(("quantity_numeric","price_numeric","fee_numeric")).issubset(names)
            revision.downgrade()
            remaining=con.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='a04_migration_test' AND table_name='paper_trades'")).scalars().all()
            assert "quantity_numeric" not in remaining
            assert con.scalar(text("SELECT price FROM a04_migration_test.paper_trades WHERE id=1"))==10.25
    finally:
        with engine.begin() as con:
            con.execute(text("DROP SCHEMA IF EXISTS a04_migration_test CASCADE"))
        engine.dispose()
