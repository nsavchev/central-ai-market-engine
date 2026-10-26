import os
import pytest
from sqlalchemy import create_engine,text
from app.paper_populated_migration import migrate_populated_paper

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable test postgres only")

def test_preserves_balances_trades_and_refuses_lossy(monkeypatch):
    assert URL and URL.endswith("/test") and "127.0.0.1" in URL
    monkeypatch.setenv("STAGE2_DISPOSABLE_DB","YES")
    engine=create_engine(URL)
    with engine.begin() as c:
        c.execute(text("CREATE TABLE paper_accounts(id int primary key,cash double precision,currency text)"))
        c.execute(text("CREATE TABLE paper_trades(id int primary key,account_id int,symbol text,side text,quantity double precision,price double precision,fee double precision)"))
        c.execute(text("INSERT INTO paper_accounts VALUES (1,999.5,'USD')"))
        c.execute(text("INSERT INTO paper_trades VALUES (1,1,'SPY','BUY',2.0,40.0,0.5)"))
    assert migrate_populated_paper(engine)=={"accounts":1,"trades":1}
    with engine.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==999.5
        assert c.scalar(text("SELECT quantity FROM paper_trades WHERE id=1"))==2
        assert c.scalar(text("SELECT mode FROM paper_write_fence WHERE id=1"))=="QUIESCED"
        assert c.scalar(text("SELECT generation FROM paper_write_fence WHERE id=1"))==1
        check=c.execute(text("""SELECT column_name, data_type, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='paper_trades'
              AND column_name IN ('quantity','price','fee')""")).all()
        assert {(r.column_name,r.data_type,r.numeric_precision,r.numeric_scale) for r in check} == {
            ('quantity','numeric',24,6),('price','numeric',20,2),('fee','numeric',20,2)}
        assert c.scalar(text("""SELECT count(*) FROM pg_constraint
            WHERE conrelid='public.paper_request_keys'::regclass
              AND contype='p'"""))==1
        assert c.scalar(text("SELECT COUNT(*) FROM paper_trades"))==1
        # Same minimum length constraint as the disposable Alembic revision.
        with pytest.raises(Exception):
            with engine.begin() as other:
                other.execute(text("""INSERT INTO paper_request_keys(account_id,request_key,fingerprint)
                    VALUES (1,'short','abc')"""))
    with engine.begin() as c:
        c.execute(text("DROP TABLE paper_request_keys"))
        c.execute(text("DROP TABLE paper_write_fence"))
        c.execute(text("DROP TABLE paper_trades"))
        c.execute(text("DROP TABLE paper_accounts"))
    engine.dispose()

def test_invalid_price_aborts_entire_migration(monkeypatch):
    assert URL and URL.endswith("/test") and "127.0.0.1" in URL
    monkeypatch.setenv("STAGE2_DISPOSABLE_DB","YES")
    engine=create_engine(URL)
    with engine.begin() as c:
        assert c.scalar(text("SELECT current_database()"))=="test"
        c.execute(text("CREATE TABLE paper_accounts(id int primary key,cash double precision,currency text)"))
        c.execute(text("CREATE TABLE paper_trades(id int primary key,account_id int,symbol text,side text,quantity double precision,price double precision,fee double precision)"))
        c.execute(text("INSERT INTO paper_accounts VALUES (1,999.5,'USD')"))
        c.execute(text("INSERT INTO paper_trades VALUES (1,1,'SPY','BUY',2.0,40.001,0.5)"))
    with pytest.raises(ValueError,match="LOSSY_OR_INVALID_DATA:paper_trades.price"):
        migrate_populated_paper(engine)
    with engine.connect() as c:
        assert c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1"))==999.5
        assert c.scalar(text("SELECT price FROM paper_trades WHERE id=1"))==40.001
        assert c.scalar(text("SELECT to_regclass('public.paper_write_fence')")) is None
        assert c.scalar(text("SELECT to_regclass('public.paper_request_keys')")) is None
        assert c.scalar(text("SELECT data_type FROM information_schema.columns WHERE table_name='paper_accounts' AND column_name='cash'"))=="double precision"
    with engine.begin() as c:
        c.execute(text("DROP TABLE paper_trades"))
        c.execute(text("DROP TABLE paper_accounts"))
    engine.dispose()

def test_invalid_nonfinite_fee_rolls_back(monkeypatch):
    assert URL and URL.endswith("/test") and "127.0.0.1" in URL
    monkeypatch.setenv("STAGE2_DISPOSABLE_DB","YES")
    engine=create_engine(URL)
    with engine.begin() as c:
        assert c.scalar(text("SELECT current_database()"))=="test"
        c.execute(text("CREATE TABLE paper_accounts(id int primary key,cash double precision,currency text)"))
        c.execute(text("CREATE TABLE paper_trades(id int primary key,account_id int,symbol text,side text,quantity double precision,price double precision,fee double precision)"))
        c.execute(text("INSERT INTO paper_accounts VALUES (1,900.0,'USD'),(2,300.0,'USD')"))
        c.execute(text("INSERT INTO paper_trades VALUES (1,1,'SPY','BUY',2.0,40.0,'NaN'::float8),(2,2,'NVDA','BUY',1.0,20.0,0.0)"))
    with pytest.raises(ValueError,match="LOSSY_OR_INVALID_DATA:paper_trades.fee"):
        migrate_populated_paper(engine)
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM paper_accounts"))==2
        assert c.scalar(text("SELECT count(*) FROM paper_trades"))==2
        assert c.scalar(text("SELECT fee::text FROM paper_trades WHERE id=1"))=="NaN"
        assert c.scalar(text("SELECT to_regclass('public.paper_write_fence')")) is None
        assert c.scalar(text("SELECT data_type FROM information_schema.columns WHERE table_name='paper_accounts' AND column_name='cash'"))=="double precision"
    with engine.begin() as c:
        c.execute(text("DROP TABLE paper_trades"))
        c.execute(text("DROP TABLE paper_accounts"))
    engine.dispose()
