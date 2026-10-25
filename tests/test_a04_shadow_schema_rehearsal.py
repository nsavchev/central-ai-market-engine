"""Disposable PostgreSQL rehearsal; never invokes the protected draft migration."""
import os
from decimal import Decimal
import pytest
from sqlalchemy import create_engine, text

URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL URL required")

@pytest.fixture
def db():
    engine = create_engine(URL)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS a04_rehearsal CASCADE"))
        c.execute(text("CREATE SCHEMA a04_rehearsal"))
        c.execute(text("CREATE TABLE a04_rehearsal.paper_accounts (id integer primary key, cash double precision)"))
        c.execute(text("""CREATE TABLE a04_rehearsal.paper_trades (
            id integer primary key, quantity double precision,
            price double precision, fee double precision)"""))
        c.execute(text("INSERT INTO a04_rehearsal.paper_accounts VALUES(1,100.25)"))
        c.execute(text("INSERT INTO a04_rehearsal.paper_trades VALUES(1,2.0,10.25,0.5)"))
    yield engine
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA a04_rehearsal CASCADE"))
    engine.dispose()

def test_additive_columns_and_rollback_preserve_old_data(db):
    with db.begin() as c:
        c.execute(text("ALTER TABLE a04_rehearsal.paper_accounts ADD COLUMN cash_numeric NUMERIC(20,2)"))
        for col, typ in (("quantity_numeric","NUMERIC(24,6)"),("price_numeric","NUMERIC(20,2)"),("fee_numeric","NUMERIC(20,2)")):
            c.execute(text(f"ALTER TABLE a04_rehearsal.paper_trades ADD COLUMN {col} {typ}"))
        assert c.scalar(text("SELECT cash FROM a04_rehearsal.paper_accounts WHERE id=1")) == 100.25
        assert c.scalar(text("SELECT cash_numeric FROM a04_rehearsal.paper_accounts WHERE id=1")) is None
        c.execute(text("UPDATE a04_rehearsal.paper_accounts SET cash_numeric=100.25 WHERE id=1"))
        c.execute(text("UPDATE a04_rehearsal.paper_trades SET quantity_numeric=2,price_numeric=10.25,fee_numeric=0.5 WHERE id=1"))
        assert c.scalar(text("SELECT cash_numeric FROM a04_rehearsal.paper_accounts WHERE id=1")) == Decimal("100.25")
    with db.begin() as c:
        c.execute(text("ALTER TABLE a04_rehearsal.paper_trades DROP COLUMN fee_numeric, DROP COLUMN price_numeric, DROP COLUMN quantity_numeric"))
        c.execute(text("ALTER TABLE a04_rehearsal.paper_accounts DROP COLUMN cash_numeric"))
        assert c.scalar(text("SELECT cash FROM a04_rehearsal.paper_accounts WHERE id=1")) == 100.25
        assert c.scalar(text("SELECT price FROM a04_rehearsal.paper_trades WHERE id=1")) == 10.25

def test_migration_does_not_touch_production_schema(db):
    with db.connect() as c:
        names = c.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='a04_rehearsal' AND table_name='paper_accounts'
        """)).scalars().all()
    assert names == ["id","cash"]

def test_draft_revision_explicitly_fails_closed():
    import importlib.util
    from pathlib import Path
    module_path = Path(__file__).resolve().parents[1] / "migrations/versions/20261025_paper_numeric_shadow.py"
    spec = importlib.util.spec_from_file_location("a04_review_only", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match="DRAFT_MIGRATION_NOT_APPROVED"):
        module.downgrade()
