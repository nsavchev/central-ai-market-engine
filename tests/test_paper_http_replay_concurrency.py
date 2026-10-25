"""Disposable HTTP concurrency and replay safety tests.

Current test service does not support idempotency keys; the replay test
documents that blocker explicitly and does not claim deduplication.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from app.paper_http_test_only import app

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL required")
HEADERS={"X-API-Token":"local-test-token"}
PAYLOAD={"symbol":"SPY","side":"BUY","quantity":"1","price":"40.00","fee":"0.00","generation":0}

@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("TEST_PAPER_API_TOKEN","local-test-token")
    db=create_engine(URL,pool_size=6)
    with db.begin() as con:
        for table in ("paper_trades","paper_accounts","paper_write_fence"):
            con.execute(text("DROP TABLE IF EXISTS "+table))
        con.execute(text("CREATE TABLE paper_write_fence(id int primary key,mode text,generation bigint)"))
        con.execute(text("CREATE TABLE paper_accounts(id int primary key,cash numeric(20,2) CHECK(cash>=0))"))
        con.execute(text("""CREATE TABLE paper_trades(
            id bigserial PRIMARY KEY, account_id int, symbol text, side text,
            quantity numeric(24,6), price numeric(20,2), fee numeric(20,2))"""))
        con.execute(text("INSERT INTO paper_write_fence VALUES(1,'LEGACY',0)"))
        con.execute(text("INSERT INTO paper_accounts VALUES(1,100.00)"))
    yield db
    with db.begin() as con:
        for table in ("paper_trades","paper_accounts","paper_write_fence"):
            con.execute(text("DROP TABLE "+table))
    db.dispose()

def post():
    with TestClient(app) as client:
        return client.post("/test-only/paper/fills",headers=HEADERS,json=PAYLOAD)

def test_concurrent_http_buys_never_overdraw(engine):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _:post(),range(4)))
    assert sorted(response.status_code for response in responses)==[200,200,422,422]
    with engine.connect() as con:
        assert con.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("20.00")
        assert con.scalar(text("SELECT COUNT(*) FROM paper_trades"))==2

def test_replay_without_key_is_current_blocker(engine):
    # No idempotency key in this test-only HTTP service: same payload is a second fill.
    first=post()
    second=post()
    assert first.status_code==second.status_code==200
    with engine.connect() as con:
        assert con.scalar(text("SELECT COUNT(*) FROM paper_trades"))==2
        assert con.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==Decimal("20.00")
