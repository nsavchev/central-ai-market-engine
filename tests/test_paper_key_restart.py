import os
import pytest
from sqlalchemy import create_engine,text
from app.paper_request_key_schema_rehearsal import create_disposable_schema
from app.paper_idempotency import idempotent_fill
URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL required")

def test_schema_and_restart_replay(monkeypatch):
    engine=create_engine(URL)
    with engine.begin() as c:
        for table in ("paper_request_keys","paper_trades","paper_accounts","paper_write_fence"):
            c.execute(text("DROP TABLE IF EXISTS "+table))
        c.execute(text("CREATE TABLE paper_write_fence(id int primary key,mode text,generation bigint)"))
        c.execute(text("CREATE TABLE paper_accounts(id int primary key,cash numeric(20,2))"))
        c.execute(text("""CREATE TABLE paper_trades(id bigserial primary key,account_id int,
            symbol text,side text,quantity numeric(24,6),price numeric(20,2),fee numeric(20,2))"""))
        create_disposable_schema(c)
        c.execute(text("INSERT INTO paper_write_fence VALUES(1,'LEGACY',0)"))
        c.execute(text("INSERT INTO paper_accounts VALUES(1,100.00)"))
    args=dict(request_key="restart-test-001",account_id=1,symbol="SPY",
              side="BUY",quantity="1",price="40",fee="0",expected_generation=0)
    original=idempotent_fill(engine,**args)
    engine.dispose()
    new_engine=create_engine(URL)
    replay=idempotent_fill(new_engine,**args)
    assert original==replay
    with new_engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM paper_trades"))==1
        assert c.scalar(text("SELECT count(*) FROM paper_request_keys"))==1
    with new_engine.begin() as c:
        for table in ("paper_request_keys","paper_trades","paper_accounts","paper_write_fence"):
            c.execute(text("DROP TABLE "+table))
    new_engine.dispose()
