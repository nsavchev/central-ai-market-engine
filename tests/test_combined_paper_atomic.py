import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from sqlalchemy import create_engine, text
from app.paper_atomic_service import record_paper_fill
from app.paper_pg_fence import quiesce

URL=os.environ.get("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL only")

@pytest.fixture
def engine():
    db=create_engine(URL,pool_size=5)
    with db.begin() as con:
        for table in ("paper_trades","paper_accounts","paper_write_fence"):
            con.execute(text("DROP TABLE IF EXISTS "+table))
        con.execute(text("CREATE TABLE paper_write_fence (id int PRIMARY KEY, mode text NOT NULL, generation bigint NOT NULL)"))
        con.execute(text("CREATE TABLE paper_accounts (id int PRIMARY KEY, cash numeric(20,2) NOT NULL CHECK(cash>=0))"))
        con.execute(text("""CREATE TABLE paper_trades (
          id bigserial PRIMARY KEY,account_id int NOT NULL REFERENCES paper_accounts(id),
          symbol text NOT NULL,side text NOT NULL,quantity numeric(24,6) NOT NULL,
          price numeric(20,2) NOT NULL,fee numeric(20,2) NOT NULL)"""))
        con.execute(text("INSERT INTO paper_write_fence VALUES(1,'LEGACY',0)"))
        con.execute(text("INSERT INTO paper_accounts VALUES(1,100.00)"))
    yield db
    with db.begin() as con:
        for table in ("paper_trades","paper_accounts","paper_write_fence"):
            con.execute(text("DROP TABLE "+table))
    db.dispose()

def buy(engine):
    return record_paper_fill(engine,account_id=1,symbol="SPY",side="BUY",quantity="1",
                             price="40.00",fee="0.00",expected_generation=0)

def test_concurrent_writes_use_fence_and_account_lock(engine):
    def attempt(_):
        try:
            buy(engine)
            return True
        except ValueError as exc:
            assert str(exc)=="INSUFFICIENT_CASH"
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt,range(4)))==2
    with engine.connect() as con:
        assert con.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("20.00")
        assert con.scalar(text("SELECT count(*) FROM paper_trades"))==2

def test_quiesce_refuses_fill_without_mutation(engine):
    with engine.begin() as con:
        quiesce(con,generation=0,approved=True)
    with pytest.raises(PermissionError,match="PAPER_WRITES_FENCED"):
        buy(engine)
    with engine.connect() as con:
        assert con.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("100.00")
        assert con.scalar(text("SELECT count(*) FROM paper_trades"))==0

def test_reject_missing_generation(engine):
    with pytest.raises(TypeError):
        record_paper_fill(engine,account_id=1,symbol="SPY",side="BUY",
                          quantity="1",price="40.00",fee="0.00")
