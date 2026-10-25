"""Execute one guarded Alembic revision on a disposable isolated schema."""
import importlib.util
import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine,text
from alembic.migration import MigrationContext
from alembic.operations import Operations

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL only")
REVISION=Path(__file__).resolve().parents[1]/"migrations/versions/a04_request_keys_test_01.py"

def load_revision():
    spec=importlib.util.spec_from_file_location("a04_request_keys_test_01",REVISION)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_upgrade_constraints_and_downgrade(monkeypatch):
    db=create_engine(URL)
    try:
        with db.begin() as con:
            con.execute(text("CREATE SCHEMA IF NOT EXISTS a04_keys_test"))
            con.execute(text("DROP TABLE IF EXISTS a04_keys_test.paper_request_keys"))
        with db.begin() as con:
            migration=load_revision()
            migration.op=Operations(MigrationContext.configure(con))
            with pytest.raises(RuntimeError,match="DISPOSABLE_TEST_SCHEMA_REQUIRED"):
                migration.upgrade()
            monkeypatch.setenv("A04_KEYS_DISPOSABLE","YES")
            monkeypatch.setenv("A04_KEYS_SCHEMA","a04_keys_test")
            migration.upgrade()
            con.execute(text("""INSERT INTO a04_keys_test.paper_request_keys
                (account_id,request_key,fingerprint) VALUES(1,'request-123',:hash)"""),
                {"hash":"a"*64})
            assert con.scalar(text("SELECT count(*) FROM a04_keys_test.paper_request_keys"))==1
            migration.downgrade()
            assert not con.scalar(text("""SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='a04_keys_test'
                AND table_name='paper_request_keys')"""))
    finally:
        with db.begin() as con:
            con.execute(text("DROP SCHEMA IF EXISTS a04_keys_test CASCADE"))
        db.dispose()
