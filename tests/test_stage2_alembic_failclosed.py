"""Alembic CLI must fail atomically when populated data would be rounded."""
import os
import subprocess
import pytest
from sqlalchemy import create_engine, text


# Local aggregate runs may omit PostgreSQL; CI must still supply its test URL.
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL") and not os.getenv("CI"),
    reason="Disposable PostgreSQL required for local execution",
)

def test_alembic_rejects_lossy_data_and_preserves_legacy_schema():
    url=os.environ["TEST_POSTGRES_URL"]
    assert url.endswith("/test") and "127.0.0.1" in url
    engine=create_engine(url)
    cols={
      "instruments":"id int primary key,symbol text,exchange text,currency text,sec_type text,primary_exchange text",
      "daily_bars":"id int primary key,instrument_id int,day date,open double precision,high double precision,low double precision,close double precision,volume double precision,source text,fetched_at timestamptz",
      "financial_snapshots":"id int primary key,symbol text,period_end date,period_type text,currency text,source text,payload json,imported_at timestamptz",
      "paper_accounts":"id int primary key,cash double precision,currency text",
      "paper_trades":"id int primary key,account_id int,symbol text,side text,quantity double precision,price double precision,fee double precision,executed_at timestamptz",
    }
    with engine.begin() as con:
        assert con.scalar(text("SELECT current_database()"))=="test"
        for name, definition in cols.items():
            con.execute(text("CREATE TABLE "+name+" ("+definition+")"))
        con.execute(text("INSERT INTO paper_accounts VALUES(1,1234.5,'USD')"))
        con.execute(text("INSERT INTO paper_trades VALUES(1,1,'SPY','BUY',2.0,55.251,0.5,NULL)"))
    run=subprocess.run(["alembic","-c","alembic-stage2.ini","upgrade","head"],
        env={**os.environ,"STAGE2_DISPOSABLE_DB":"YES"},capture_output=True,text=True)
    assert run.returncode!=0
    assert "LOSSY_OR_INVALID_DATA:paper_trades.price" in (run.stderr+run.stdout)
    with engine.connect() as con:
        assert con.scalar(text("SELECT to_regclass('public.alembic_version')")) is None
        assert con.scalar(text("SELECT to_regclass('public.paper_write_fence')")) is None
        assert con.scalar(text("SELECT to_regclass('public.paper_request_keys')")) is None
        assert con.scalar(text("SELECT price FROM paper_trades WHERE id=1"))==55.251
        assert con.scalar(text("""SELECT data_type FROM information_schema.columns
            WHERE table_schema='public' AND table_name='paper_accounts' AND column_name='cash'"""))=="double precision"
    engine.dispose()
