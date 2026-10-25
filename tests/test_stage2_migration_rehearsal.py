"""Disposable PostgreSQL migration rehearsal; no production schema or URL."""
import os
import pytest
from sqlalchemy import create_engine, text
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from migrations.versions import stage2_paper_test_001 as migration

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="CI disposable PostgreSQL required")

def test_upgrade_and_downgrade_rehearsal(monkeypatch):
    assert URL and URL.endswith("/test") and "127.0.0.1" in URL
    monkeypatch.setenv("STAGE2_DISPOSABLE_DB","YES")
    engine=create_engine(URL)
    with engine.begin() as con:
        assert con.scalar(text("SELECT current_database()"))=="test"
        con.execute(text("CREATE TABLE paper_accounts(id integer PRIMARY KEY,cash double precision,currency varchar(8))"))
        con.execute(text("CREATE TABLE paper_trades(id bigserial PRIMARY KEY,account_id integer,symbol varchar(32),side varchar(4),quantity double precision,price double precision,fee double precision)"))
        ctx=MigrationContext.configure(con)
        with Operations.context(ctx):
            migration.upgrade()
        fields=con.execute(text("""
            SELECT table_name,column_name,data_type,numeric_precision,numeric_scale
            FROM information_schema.columns WHERE table_schema='public'
            AND ((table_name='paper_accounts' AND column_name='cash')
              OR (table_name='paper_trades' AND column_name IN ('quantity','price','fee')))
        """)).all()
        assert len(fields)==4
        assert all(row.data_type=="numeric" for row in fields)
        assert con.scalar(text("SELECT mode FROM paper_write_fence WHERE id=1"))=="LEGACY"
        assert con.scalar(text("SELECT to_regclass('public.paper_request_keys')")) is not None
        with Operations.context(ctx):
            migration.downgrade()
        assert con.scalar(text("SELECT to_regclass('public.paper_request_keys')")) is None
        assert con.scalar(text("SELECT to_regclass('public.paper_write_fence')")) is None
        con.execute(text("DROP TABLE paper_trades"))
        con.execute(text("DROP TABLE paper_accounts"))
    engine.dispose()
