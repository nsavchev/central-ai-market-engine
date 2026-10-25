import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
from app.paper_http_test_only import app
URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL required")
BODY={"symbol":"SPY","side":"BUY","quantity":"1","price":"40.00","fee":"0","generation":0}
HEADERS={"X-API-Token":"local-test-token","Idempotency-Key":"test-request-001"}
@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("TEST_PAPER_API_TOKEN","local-test-token")
    engine=create_engine(URL,pool_size=6)
    with engine.begin() as c:
        for table in ("paper_request_keys","paper_trades","paper_accounts","paper_write_fence"):
            c.execute(text("DROP TABLE IF EXISTS "+table))
        c.execute(text("CREATE TABLE paper_write_fence(id int PRIMARY KEY,mode text,generation bigint)"))
        c.execute(text("CREATE TABLE paper_accounts(id int PRIMARY KEY,cash numeric(20,2))"))
        c.execute(text("""CREATE TABLE paper_trades(id bigserial PRIMARY KEY,account_id int,symbol text,
                         side text,quantity numeric(24,6),price numeric(20,2),fee numeric(20,2))"""))
        c.execute(text("""CREATE TABLE paper_request_keys(account_id int,request_key text,fingerprint text,
                          result jsonb,PRIMARY KEY(account_id,request_key))"""))
        c.execute(text("INSERT INTO paper_write_fence VALUES(1,'LEGACY',0)"))
        c.execute(text("INSERT INTO paper_accounts VALUES(1,100.00)"))
    yield engine
    with engine.begin() as c:
        for table in ("paper_request_keys","paper_trades","paper_accounts","paper_write_fence"):
            c.execute(text("DROP TABLE "+table))
    engine.dispose()
def post(body=BODY,headers=HEADERS):
    with TestClient(app) as client:
        return client.post("/test-only/paper/idempotent-fills",json=body,headers=headers)
def count(db):
    with db.connect() as c:
        return c.scalar(text("SELECT count(*) FROM paper_trades"))
def test_retry_single_fill(db):
    a,b=post(),post()
    assert a.status_code==b.status_code==200
    assert a.json()==b.json()
    assert count(db)==1
def test_concurrent_identical_http(db):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _:post(),range(4)))
    assert all(x.status_code==200 for x in responses)
    assert count(db)==1
def test_same_key_different_payload_conflicts(db):
    assert post().status_code==200
    assert post({**BODY,"price":"41.00"}).status_code==409
    assert count(db)==1
def test_missing_key_and_auth_denied(db):
    assert post(headers={"X-API-Token":"local-test-token"}).status_code==422
    assert post(headers={"Idempotency-Key":"test-request-001"}).status_code==401
    assert count(db)==0
def test_fenced_http_rolls_back_request_key(db):
    with db.begin() as c:
        c.execute(text("UPDATE paper_write_fence SET mode='QUIESCED',generation=1 WHERE id=1"))
    assert post().status_code==409
    with db.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM paper_request_keys"))==0
