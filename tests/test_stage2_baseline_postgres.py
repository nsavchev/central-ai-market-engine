"""Real backend regression tests on a dedicated, initially empty CI database."""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

import app.paper_migration_baseline as baseline


@pytest.fixture
def engine():
    value = os.getenv("TEST_POSTGRES_URL")
    if not value:
        pytest.skip("Disposable PostgreSQL URL not supplied")
    url = make_url(value)
    if (os.getenv("STAGE2_DISPOSABLE_DB") != "YES"
        or url.drivername != "postgresql+psycopg"
        or url.host not in ("127.0.0.1", "localhost") or url.database != "test"):
        pytest.fail("REFUSE_NON_DISPOSABLE_DATABASE")
    engine = create_engine(url)
    owned = False
    try:
        with engine.begin() as con:
            assert con.scalar(text("SELECT current_database()")) == "test"
            assert inspect(con).get_table_names(schema="public") == []
            sql = (Path(__file__).parent / "fixtures/vps_legacy_schema_20261103.sql").read_text()
            for statement in sql.split(";"):
                if statement.strip():
                    con.exec_driver_sql(statement)
        owned = True
        yield engine
    finally:
        if owned:
            with engine.begin() as con:
                # Only this fixture's five tables; owned sequences drop with them.
                con.exec_driver_sql("DROP TABLE public.paper_trades, public.paper_accounts, "
                    "public.daily_bars, public.financial_snapshots, public.instruments")
        engine.dispose()


def test_vps_fixture_is_read_in_repeatable_read_only_transaction(engine, monkeypatch):
    original = baseline.inspect
    observed = []
    def checked_inspect(con):
        observed.append((con.scalar(text("SHOW transaction_read_only")),
                         con.scalar(text("SHOW transaction_isolation"))))
        return original(con)
    monkeypatch.setattr(baseline, "inspect", checked_inspect)
    assert baseline.inspect_legacy_baseline(engine) == {
        "baseline_eligible": True, "errors": [],
        "paper_counts": {"paper_accounts": 0, "paper_trades": 0}}
    assert observed == [("on", "repeatable read")]
    # The read-only flag must not leak into subsequent writer connections.
    with engine.begin() as con:
        con.exec_driver_sql("INSERT INTO paper_accounts(cash,currency) VALUES(100,'USD')")
    assert baseline.inspect_legacy_baseline(engine)["paper_counts"]["paper_accounts"] == 1


def test_accidental_write_during_inspection_is_rejected_by_postgres(engine, monkeypatch):
    def attempting_inspect(con):
        con.exec_driver_sql("INSERT INTO paper_accounts(cash,currency) VALUES(100,'USD')")
    monkeypatch.setattr(baseline, "inspect", attempting_inspect)
    with pytest.raises(DBAPIError) as error:
        baseline.inspect_legacy_baseline(engine)
    assert error.value.orig.sqlstate == "25006"
    with engine.connect() as con:
        assert con.scalar(text("SELECT count(*) FROM paper_accounts")) == 0


def test_numeric_drift_is_rejected(engine):
    with engine.begin() as con:
        con.exec_driver_sql("ALTER TABLE paper_accounts ALTER COLUMN cash TYPE numeric(20,2)")
    result = baseline.inspect_legacy_baseline(engine)
    assert not result["baseline_eligible"]
    assert "UNEXPECTED_LEGACY_TYPE:paper_accounts.cash" in result["errors"]


def test_missing_column_is_rejected(engine):
    with engine.begin() as con:
        con.exec_driver_sql("ALTER TABLE paper_trades DROP COLUMN executed_at")
    result = baseline.inspect_legacy_baseline(engine)
    assert not result["baseline_eligible"]
    assert "MISSING_COLUMN:paper_trades.executed_at" in result["errors"]
