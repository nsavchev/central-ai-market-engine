"""Exercise schema contract against real PostgreSQL FK and UNIQUE constraints."""
import os
import pytest
from sqlalchemy import create_engine, text
from app.paper_schema_constraints import inspect_relational_constraints

URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL required")

def test_real_postgres_relational_contract():
    assert URL and URL.endswith("/test") and "127.0.0.1" in URL
    engine = create_engine(URL)
    with engine.begin() as c:
        assert c.scalar(text("SELECT current_database()")) == "test"
        c.execute(text("""CREATE TABLE instruments(
            id integer primary key, symbol varchar(32), exchange varchar(32),
            currency varchar(8), sec_type varchar(12), primary_exchange varchar(32),
            CONSTRAINT uq_instrument UNIQUE(symbol,exchange,currency,sec_type,primary_exchange))"""))
        c.execute(text("""CREATE TABLE daily_bars(
            id integer primary key, instrument_id integer REFERENCES instruments(id),
            day date, source varchar(24), open double precision, high double precision,
            low double precision, close double precision, volume double precision,
            fetched_at timestamptz,
            CONSTRAINT uq_daily_bar UNIQUE(instrument_id,day,source))"""))
        c.execute(text("""CREATE TABLE financial_snapshots(
            id integer primary key, symbol varchar(32), period_end date,
            period_type varchar(8), currency varchar(3), source varchar(40),
            payload json, imported_at timestamptz,
            CONSTRAINT uq_financial UNIQUE(symbol,period_end,period_type,currency,source))"""))
        c.execute(text("""CREATE TABLE paper_accounts(
            id integer primary key, cash double precision, currency varchar(8))"""))
        c.execute(text("""CREATE TABLE paper_trades(
            id integer primary key, account_id integer REFERENCES paper_accounts(id),
            symbol varchar(32), side varchar(4), quantity double precision,
            price double precision, fee double precision, executed_at timestamptz)"""))
    try:
        result = inspect_relational_constraints(engine)
        assert result == {"ready": True, "errors": []}
        with engine.begin() as c:
            c.execute(text("ALTER TABLE paper_trades DROP CONSTRAINT paper_trades_account_id_fkey"))
        result = inspect_relational_constraints(engine)
        assert not result["ready"]
        assert any(e.startswith("MISSING_FOREIGN_KEY:paper_trades:") for e in result["errors"])
    finally:
        with engine.begin() as c:
            for table in ("paper_trades","paper_accounts","financial_snapshots","daily_bars","instruments"):
                c.execute(text("DROP TABLE IF EXISTS "+table))
        engine.dispose()
