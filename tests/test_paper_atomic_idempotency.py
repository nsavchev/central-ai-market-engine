import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from sqlalchemy import create_engine,text
from app.paper_idempotency import idempotent_fill
URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL required")
@pytest.fixture
def engine():
    engine=create_engine(URL,pool_size=5)
    with engine.begin() as c:
        for table in ("paper_request_keys","paper_trades","paper_accounts","paper_write_fence"):
            c.execute(text("DROP TABLE IF EXISTS "+table))
        c.execute(text("CREATE TABLE paper_write_fence(id int PRIMARY KEY,mode text,generation bigint)"))
        c.execute(text("CREATE TABLE paper_accounts(id int PRIMARY KEY,cash numeric(20,2))"))
        c.execute(text("""CREATE TABLE paper_trades(id bigserial PRIMARY KEY,account_id int,symbol text,side text,
              quantity numeric(24,6),price numeric(20,2),fee numeric(20,2))"""))
        c.execute(text("""CREATE TABLE paper_request_keys(
          account_id int NOT NULL, request_key text NOT NULL, fingerprint text NOT NULL,
          result jsonb, PRIMARY KEY(account_id,request_key))"""))
        c.execute(text("INSERT INTO paper_write_fence VALUES(1,'LEGACY',0)"))
        c.execute(text("INSERT INTO paper_accounts VALUES(1,100.00)"))
    yield engine
    with engine.begin() as c:
        for table in ("paper_request_keys","paper_trades","paper_accounts","paper_write_fence"):
            c.execute(text("DROP TABLE "+table))
    engine.dispose()
def call(engine,key="request-001",price="40.00"):
    return idempotent_fill(engine,request_key=key,account_id=1,symbol="SPY",side="BUY",
                           quantity="1",price=price,fee="0",expected_generation=0)
def test_replay_returns_same_result_and_one_trade(engine):
    assert call(engine)==call(engine,price="40")
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM paper_trades"))==1
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("60.00")
def test_key_reuse_for_different_payload_rejected(engine):
    call(engine)
    with pytest.raises(ValueError,match="IDEMPOTENCY_KEY_CONFLICT"):
        call(engine,price="41.00")
def test_concurrent_identical_requests_only_one_trade(engine):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:call(engine),range(4)))
    assert len({x["cash"] for x in results})==1
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM paper_trades"))==1
def test_fenced_request_rolls_back_reservation(engine):
    with engine.begin() as c:
        c.execute(text("UPDATE paper_write_fence SET mode='QUIESCED',generation=1 WHERE id=1"))
    with pytest.raises(PermissionError):
        call(engine)
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM paper_request_keys"))==0
