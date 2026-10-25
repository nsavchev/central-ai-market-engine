"""Disposable PostgreSQL tests; no live account, broker or production migration."""
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL required")


@pytest.fixture
def engine():
    db = create_engine(URL, pool_size=5, max_overflow=0)
    with db.begin() as con:
        con.execute(text("CREATE TEMP TABLE IF NOT EXISTS ignored_marker (x integer)"))
        con.execute(text("DROP TABLE IF EXISTS paper_a03_test"))
        con.execute(text("""CREATE TABLE paper_a03_test (
            id integer PRIMARY KEY,
            cash numeric(20,2) NOT NULL CHECK(cash >= 0),
            shares numeric(24,6) NOT NULL CHECK(shares >= 0)
        )"""))
        con.execute(text("INSERT INTO paper_a03_test VALUES (1, 100.00, 0)"))
    yield db
    with db.begin() as con:
        con.execute(text("DROP TABLE IF EXISTS paper_a03_test"))
    db.dispose()


def test_numeric_precision(engine):
    with engine.begin() as con:
        con.execute(text("UPDATE paper_a03_test SET cash = cash - :cost, shares=shares+:qty WHERE id=1"),
                    {"cost": Decimal("0.10"), "qty": Decimal("0.100000")})
        row = con.execute(text("SELECT cash, shares FROM paper_a03_test WHERE id=1")).one()
    assert row == (Decimal("99.90"), Decimal("0.100000"))


def _buy(engine, cost):
    with engine.begin() as con:
        row = con.execute(text("SELECT cash FROM paper_a03_test WHERE id=1 FOR UPDATE")).one()
        if row[0] < cost:
            return False
        con.execute(text("UPDATE paper_a03_test SET cash=cash-:cost, shares=shares+1 WHERE id=1"),
                    {"cost": cost})
        return True


def test_concurrent_purchases_preserve_balance(engine):
    with ThreadPoolExecutor(max_workers=4) as pool:
        accepted = list(pool.map(lambda _: _buy(engine, Decimal("40.00")), range(4)))
    assert sum(accepted) == 2
    with engine.connect() as con:
        row = con.execute(text("SELECT cash, shares FROM paper_a03_test WHERE id=1")).one()
    assert row == (Decimal("20.00"), Decimal("2.000000"))


def test_negative_balance_rejected(engine):
    with pytest.raises(Exception):
        with engine.begin() as con:
            con.execute(text("UPDATE paper_a03_test SET cash=-1 WHERE id=1"))
    with engine.connect() as con:
        assert con.scalar(text("SELECT cash FROM paper_a03_test WHERE id=1")) == Decimal("100.00")
