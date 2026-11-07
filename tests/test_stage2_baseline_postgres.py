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


@pytest.fixture
def runtime_engine(engine):
    """Real authenticated non-owner login; never SET ROLE from an admin session."""
    from uuid import uuid4
    role = "ci_runtime_" + uuid4().hex
    password = uuid4().hex + uuid4().hex  # Disposable CI credential only.
    privileges = {
        "instruments": "SELECT, INSERT",
        "daily_bars": "SELECT, INSERT, UPDATE",
        "financial_snapshots": "SELECT, INSERT, UPDATE",
        "paper_accounts": "SELECT, INSERT, UPDATE",
        "paper_trades": "SELECT, INSERT",
    }
    created = False
    runtime = None
    try:
        with engine.begin() as con:
            assert con.scalar(text("SELECT current_database()")) == "test"
            # Generated hex-only identifiers/password; no operator data or secrets.
            con.exec_driver_sql(
                f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\' '
                'NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT'
            )
            con.exec_driver_sql(f'GRANT CONNECT ON DATABASE test TO "{role}"')
            con.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            for table, allowed in privileges.items():
                con.exec_driver_sql(f'GRANT {allowed} ON TABLE public.{table} TO "{role}"')
                con.exec_driver_sql(f'GRANT USAGE ON SEQUENCE public.{table}_id_seq TO "{role}"')
        created = True
        runtime = create_engine(
            engine.url.set(username=role, password=password), hide_parameters=True,
            connect_args={"options": "-c statement_timeout=10000 -c lock_timeout=2000"},
        )
        yield runtime
    finally:
        if runtime is not None:
            runtime.dispose()
        if created:
            with engine.begin() as con:
                # Revoke only this random, newly created test role's grants.
                con.exec_driver_sql(f'DROP OWNED BY "{role}"')
                con.exec_driver_sql(f'DROP ROLE "{role}"')


def test_runtime_login_commits_required_legacy_dml_without_admin_rights(runtime_engine):
    with runtime_engine.begin() as con:
        identity = con.execute(text("""
            SELECT current_user=session_user,
                   rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit
            FROM pg_roles WHERE rolname=current_user
        """)).one()
        assert tuple(identity) == (True, False, False, False, False, False, False)
        assert not con.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')"))
        assert not con.scalar(text("""
            SELECT EXISTS(SELECT 1 FROM pg_auth_members
                          WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user))
        """))
        instrument = con.scalar(text("""
            INSERT INTO instruments(symbol,exchange,currency,sec_type,primary_exchange)
            VALUES('CI','SMART','USD','STK','') RETURNING id
        """))
        con.execute(text("""
            INSERT INTO daily_bars(instrument_id,day,open,high,low,close,volume,source,fetched_at)
            VALUES(:instrument,'2020-01-01',10,12,9,11,100,'CI',CURRENT_TIMESTAMP)
        """), {"instrument": instrument})
        con.exec_driver_sql("UPDATE daily_bars SET close=12")
        con.exec_driver_sql("""
            INSERT INTO financial_snapshots(symbol,period_end,period_type,currency,source,payload,imported_at)
            VALUES('CI','2019-12-31','FY','USD','CI','{}',CURRENT_TIMESTAMP)
        """)
        con.exec_driver_sql("UPDATE financial_snapshots SET payload='{\"fixture\":true}'")
        account = con.scalar(text("INSERT INTO paper_accounts(cash,currency) VALUES(100,'USD') RETURNING id"))
        con.execute(text("UPDATE paper_accounts SET cash=90 WHERE id=:id"), {"id": account})
        con.execute(text("""
            INSERT INTO paper_trades(account_id,symbol,side,quantity,price,fee,executed_at)
            VALUES(:account,'CI','BUY',1,10,0,CURRENT_TIMESTAMP)
        """), {"account": account})
    # Force a fresh backend/login to verify committed visibility across sessions.
    runtime_engine.dispose()
    with runtime_engine.connect() as con:
        for table in baseline.REQUIRED:
            assert con.scalar(text(f"SELECT count(*) FROM public.{table}")) == 1
            assert not con.scalar(text(
                f"SELECT has_table_privilege(current_user,'public.{table}','SELECT WITH GRANT OPTION')"))
        assert con.scalar(text("SELECT cash FROM paper_accounts")) == 90
        assert con.scalar(text("SELECT close FROM daily_bars")) == 12


def test_runtime_login_cannot_delete_or_change_schema_roles_or_sequences(runtime_engine, engine):
    forbidden = [f"DELETE FROM public.{table}" for table in baseline.REQUIRED]
    forbidden += [
        "TRUNCATE public.paper_trades",
        "UPDATE public.instruments SET symbol='DENIED'",
        "UPDATE public.paper_trades SET price=0",
        "CREATE TABLE public.ci_forbidden(id integer)",
        "ALTER TABLE public.paper_accounts ADD COLUMN ci_forbidden integer",
        "DROP TABLE public.paper_trades",
        "ALTER SEQUENCE public.paper_trades_id_seq RESTART WITH 100",
        "SELECT setval('public.paper_trades_id_seq',100,false)",
        "CREATE ROLE ci_forbidden_role",
    ]
    with runtime_engine.connect() as con:
        role = con.scalar(text("SELECT current_user"))
    forbidden.append(f'ALTER ROLE "{role}" SUPERUSER')
    with engine.connect() as con:
        admin = con.scalar(text("SELECT current_user"))
    # Quote the backend-provided identifier; a real login cannot RESET/SET into its provisioner.
    quoted_admin = admin.replace('"', '""')
    forbidden.append(f'SET LOCAL ROLE "{quoted_admin}"')
    for statement in forbidden:
        with pytest.raises(DBAPIError) as error:
            with runtime_engine.begin() as con:
                con.exec_driver_sql(statement)
        assert error.value.orig.sqlstate == "42501", statement


def test_prepare_only_generated_role_sql_on_disposable_schema(engine):
    from uuid import uuid4
    from scripts.market_role_cutover_prepare import role_sql
    role = "market_runtime_" + uuid4().hex[:12]
    sql = role_sql(role, uuid4().hex + uuid4().hex, "test")
    created = False
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as con:
            try:
                con.exec_driver_sql(sql)
                created = True
            except Exception:
                con.exec_driver_sql("ROLLBACK")
                raise
            assert con.scalar(text("SELECT NOT rolsuper AND NOT rolcreatedb AND NOT "
                "rolcreaterole AND NOT rolreplication AND NOT rolbypassrls AND NOT rolinherit "
                "FROM pg_roles WHERE rolname=:role"), {"role": role})
            assert con.scalar(text("SELECT has_table_privilege(:role,'public.paper_accounts','UPDATE')"),
                              {"role": role})
            assert not con.scalar(text("SELECT has_table_privilege(:role,'public.paper_trades','UPDATE')"),
                                  {"role": role})
    finally:
        if created:
            with engine.begin() as con:
                con.exec_driver_sql(f'DROP OWNED BY "{role}"')
                con.exec_driver_sql(f'DROP ROLE "{role}"')
