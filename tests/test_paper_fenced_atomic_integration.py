import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from sqlalchemy import create_engine,text
from app.paper_pg_fence import quiesce
from app.paper_fenced_atomic_test_service import fenced_buy

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL only")

@pytest.fixture
def engine():
    db=create_engine(URL,pool_size=5)
    with db.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS paper_trades"))
        c.execute(text("DROP TABLE IF EXISTS paper_accounts"))
        c.execute(text("DROP TABLE IF EXISTS paper_write_fence"))
        c.execute(text("CREATE TABLE paper_write_fence(id int primary key,mode text,generation bigint)"))
        c.execute(text("CREATE TABLE paper_accounts(id int primary key,cash numeric(20,2) NOT NULL CHECK(cash>=0))"))
        c.execute(text("CREATE TABLE paper_trades(id bigserial primary key,cost numeric(20,2))"))
        c.execute(text("INSERT INTO paper_write_fence VALUES(1,'LEGACY',0)"))
        c.execute(text("INSERT INTO paper_accounts VALUES(1,100)"))
    yield db
    with db.begin() as c:
        c.execute(text("DROP TABLE paper_trades"))
        c.execute(text("DROP TABLE paper_accounts"))
        c.execute(text("DROP TABLE paper_write_fence"))
    db.dispose()

def test_parallel_fenced_buys(engine):
    def attempt(_):
        try:
            fenced_buy(engine,generation=0,cost="40.00")
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(attempt,range(4)))
    assert sum(results)==2
    with engine.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("20.00")
        assert c.scalar(text("SELECT count(*) FROM paper_trades"))==2

def test_quiesce_prevents_new_write(engine):
    with engine.begin() as c:
        quiesce(c,generation=0,approved=True)
    with pytest.raises(PermissionError,match="PAPER_WRITES_FENCED"):
        fenced_buy(engine,generation=0,cost="1.00")
    with engine.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("100.00")

def test_insert_failure_rolls_back_cash(engine):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE paper_trades ADD CONSTRAINT reject_cost CHECK(cost < 0)"))
    with pytest.raises(Exception):
        fenced_buy(engine,generation=0,cost="10.00")
    with engine.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("100.00")
