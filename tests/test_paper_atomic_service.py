import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from sqlalchemy import create_engine,text
from app.paper_atomic_service import record_paper_fill

URL=os.environ.get("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable postgres required")

@pytest.fixture
def engine():
    eng=create_engine(URL,pool_size=5)
    with eng.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS paper_trades"))
        c.execute(text("DROP TABLE IF EXISTS paper_accounts"))
        c.execute(text("CREATE TABLE paper_accounts(id integer PRIMARY KEY,cash numeric(20,2) NOT NULL CHECK(cash>=0))"))
        c.execute(text("""CREATE TABLE paper_trades (
          id bigserial PRIMARY KEY,account_id integer NOT NULL REFERENCES paper_accounts(id),
          symbol text NOT NULL,side text NOT NULL,quantity numeric(24,6) NOT NULL,
          price numeric(20,2) NOT NULL,fee numeric(20,2) NOT NULL)"""))
        c.execute(text("INSERT INTO paper_accounts VALUES(1,100.00)"))
    yield eng
    with eng.begin() as c:
        c.execute(text("DROP TABLE paper_trades"))
        c.execute(text("DROP TABLE paper_accounts"))
    eng.dispose()

def call(eng,**kwargs):
    return record_paper_fill(eng,account_id=1,symbol="SPY",side="BUY",quantity=1,price="40.00",fee="0.00",**kwargs)

def test_concurrent_purchases_are_serialized(engine):
    with ThreadPoolExecutor(max_workers=4) as pool:
        def attempt(_):
            try:return call(engine)["cash"]
            except ValueError as e:return str(e)
        results=list(pool.map(attempt,range(4)))
    assert len([x for x in results if x!="INSUFFICIENT_CASH"])==2
    with engine.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("20.00")
        assert c.scalar(text("SELECT COUNT(*) FROM paper_trades"))==2

def test_failed_sell_does_not_mutate(engine):
    with pytest.raises(ValueError,match="INSUFFICIENT_SHARES"):
        record_paper_fill(engine,account_id=1,symbol="SPY",side="SELL",quantity=1,price="40.00",fee=0)
    with engine.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("100.00")
        assert c.scalar(text("SELECT COUNT(*) FROM paper_trades"))==0

def test_rollback_on_trade_insert_error(engine):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE paper_trades ADD CONSTRAINT deny_buy CHECK(side='SELL')"))
    with pytest.raises(Exception):
        call(engine)
    with engine.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("100.00")
