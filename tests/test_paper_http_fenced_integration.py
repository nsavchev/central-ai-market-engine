import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
from app.paper_http_test_only import app

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL only")

@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("TEST_PAPER_API_TOKEN","local-test-token")
    engine=create_engine(URL)
    with engine.begin() as c:
        for table in ("paper_trades","paper_accounts","paper_write_fence"):
            c.execute(text("DROP TABLE IF EXISTS "+table))
        c.execute(text("CREATE TABLE paper_write_fence(id int primary key,mode text,generation bigint)"))
        c.execute(text("CREATE TABLE paper_accounts(id int primary key,cash numeric(20,2))"))
        c.execute(text("""CREATE TABLE paper_trades(
          id bigserial PRIMARY KEY,account_id int,symbol text,side text,
          quantity numeric(24,6),price numeric(20,2),fee numeric(20,2),executed_at timestamptz NOT NULL)"""))
        c.execute(text("INSERT INTO paper_write_fence VALUES(1,'LEGACY',0)"))
        c.execute(text("INSERT INTO paper_accounts VALUES(1,100.00)"))
    yield engine
    with engine.begin() as c:
        for table in ("paper_trades","paper_accounts","paper_write_fence"):
            c.execute(text("DROP TABLE "+table))
    engine.dispose()

def payload():
    return {"symbol":"SPY","side":"BUY","quantity":"1","price":"40.00","fee":"0.00","generation":0}

def test_authentication_blocks_write(db):
    with TestClient(app) as c:
        response=c.post("/test-only/paper/fills",json=payload())
    assert response.status_code==401
    with db.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==100

def test_authenticated_atomic_fill(db):
    with TestClient(app) as c:
        response=c.post("/test-only/paper/fills",json=payload(),headers={"X-API-Token":"local-test-token"})
    assert response.status_code==200,response.text
    assert response.json()["cash"]=="60.00"

def test_quiesced_state_blocks_http_mutation(db):
    with db.begin() as c:
        c.execute(text("UPDATE paper_write_fence SET mode='QUIESCED',generation=1 WHERE id=1"))
    with TestClient(app) as c:
        response=c.post("/test-only/paper/fills",json=payload(),headers={"X-API-Token":"local-test-token"})
    assert response.status_code==409
    with db.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==100
