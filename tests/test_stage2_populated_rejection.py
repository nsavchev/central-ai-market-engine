"""Migration must reject populated paper tables without losing existing records."""
import os
import pytest
from sqlalchemy import create_engine,text
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from migrations.versions import stage2_paper_test_001 as migration

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable CI PostgreSQL only")

def test_populated_legacy_schema_is_rejected_without_mutation(monkeypatch):
    if not URL or not URL.endswith("/test") or "127.0.0.1" not in URL:
        pytest.fail("CI disposable test DB required")
    monkeypatch.setenv("STAGE2_DISPOSABLE_DB","YES")
    engine=create_engine(URL)
    with engine.begin() as con:
        assert con.scalar(text("SELECT current_database()"))=="test"
        con.execute(text("CREATE TABLE paper_accounts(id int primary key,cash double precision,currency text)"))
        con.execute(text("CREATE TABLE paper_trades(id int primary key,account_id int,symbol text,side text,quantity double precision,price double precision,fee double precision)"))
        con.execute(text("INSERT INTO paper_accounts VALUES (1,1357.25,'USD')"))
        con.execute(text("INSERT INTO paper_trades VALUES (1,1,'SPY','BUY',2,100.25,0.5)"))
        ctx=MigrationContext.configure(con)
        with Operations.context(ctx):
            with pytest.raises(RuntimeError,match="PAPER_TABLES_NOT_EMPTY"):
                migration.upgrade()
        assert con.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==1357.25
        assert con.scalar(text("SELECT quantity FROM paper_trades WHERE id=1"))==2.0
        assert con.scalar(text("SELECT to_regclass('public.paper_request_keys')")) is None
        assert con.scalar(text("SELECT to_regclass('public.paper_write_fence')")) is None
        con.execute(text("DROP TABLE paper_trades"))
        con.execute(text("DROP TABLE paper_accounts"))
    engine.dispose()
