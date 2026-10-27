"""Real app.main FastAPI route, disposable PostgreSQL only.

Do NOT invoke against market or market_restore_test. No lifespan/startup
is executed; the v2 test engine is injected explicitly.
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
from app import main
from app.paper_account_bootstrap import bootstrap_paper_account

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL required")
AUTH={"X-API-Token":"stage1-ci-token","Idempotency-Key":"http-e2e-request-001"}
BUY={"symbol":"SPY","side":"BUY","quantity":"2","price":"40.00","fee":"1.00","generation":0}

@pytest.fixture
def db(monkeypatch):
    if not URL or not URL.endswith("/test"):
        pytest.fail("Refusing non-disposable PostgreSQL database")
    eng=create_engine(URL)
    with eng.begin() as con:
        for table in ("paper_request_keys","paper_trades","paper_accounts","paper_write_fence"):
            con.execute(text("DROP TABLE IF EXISTS "+table))
        con.execute(text("CREATE TABLE paper_accounts(id integer PRIMARY KEY,cash numeric(20,2) NOT NULL,currency varchar(8))"))
        con.execute(text("""CREATE TABLE paper_trades(id bigserial PRIMARY KEY,
            account_id int REFERENCES paper_accounts(id),symbol varchar(32),
            side varchar(4),quantity numeric(24,6),price numeric(20,2),fee numeric(20,2),executed_at timestamptz NOT NULL)"""))
        con.execute(text("""CREATE TABLE paper_write_fence(id int PRIMARY KEY,
            mode text NOT NULL,generation bigint NOT NULL)"""))
        con.execute(text("""CREATE TABLE paper_request_keys(account_id bigint,request_key varchar(128),
            fingerprint varchar(64),result jsonb, PRIMARY KEY(account_id,request_key))"""))
        con.execute(text("INSERT INTO paper_write_fence VALUES (1,'LEGACY',0)"))
    bootstrap_paper_account(eng,initial_cash="100.00")
    monkeypatch.setattr(main,"_paper_engine",eng)
    monkeypatch.setenv("PAPER_V2_ENABLED","YES")
    monkeypatch.setenv("PAPER_V2_DATABASE_NAME","test")
    yield eng
    with eng.begin() as con:
        for table in ("paper_request_keys","paper_trades","paper_accounts","paper_write_fence"):
            con.execute(text("DROP TABLE "+table))
    eng.dispose()

def send(body,headers=AUTH):
    # No context manager: app lifespan would invoke main.init_db on unrelated
    # configured DATABASE_URL; this tests HTTP routing only.
    return TestClient(main.app).post("/paper/v2/trades",headers=headers,json=body)

def test_http_buy_replay_sell_and_no_double_fill(db):
    first=send(BUY)
    assert first.status_code==200,first.text
    assert first.json()["cash"]=="19.00"
    replay=send(BUY)
    assert replay.status_code==200
    assert replay.json()==first.json()
    sell=send({**BUY,"side":"SELL","quantity":"1","price":"50.00","fee":"0"},
              {**AUTH,"Idempotency-Key":"http-e2e-request-002"})
    assert sell.status_code==200,sell.text
    assert sell.json()["cash"]=="69.00"
    with db.connect() as con:
        assert con.scalar(text("SELECT COUNT(*) FROM paper_trades"))==2

def test_http_conflict_and_fence(db):
    assert send(BUY).status_code==200
    assert send({**BUY,"price":"41.00"}).status_code==409
    with db.begin() as con:
        con.execute(text("UPDATE paper_write_fence SET mode='QUIESCED',generation=1 WHERE id=1"))
    rejected=send(BUY,{**AUTH,"Idempotency-Key":"http-e2e-request-003"})
    assert rejected.status_code==409,rejected.text
    with db.connect() as con:
        assert con.scalar(text("SELECT COUNT(*) FROM paper_trades"))==1
        assert con.scalar(text("SELECT COUNT(*) FROM paper_request_keys"))==1

def test_legacy_route_blocked_and_auth_required(db):
    assert TestClient(main.app).post("/paper/trades",headers=AUTH,
        json={"symbol":"SPY","side":"BUY","quantity":1,"price":40}).status_code==409
    assert send(BUY,{"Idempotency-Key":"http-e2e-request-001"}).status_code==401
    with db.connect() as con:
        assert con.scalar(text("SELECT COUNT(*) FROM paper_trades"))==0
