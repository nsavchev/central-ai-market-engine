import os
import pytest
from sqlalchemy import create_engine,text
from app.paper_existing_data_report import report
URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL required")
def test_read_only_precision_report():
    engine=create_engine(URL)
    with engine.begin() as con:
        con.execute(text("CREATE TEMP TABLE ignored(x int)"))
        con.execute(text("DROP TABLE IF EXISTS paper_accounts"))
        con.execute(text("DROP TABLE IF EXISTS paper_trades"))
        con.execute(text("CREATE TABLE paper_accounts(cash double precision)"))
        con.execute(text("CREATE TABLE paper_trades(quantity double precision,price double precision,fee double precision)"))
        con.execute(text("INSERT INTO paper_accounts VALUES (100.25),(100.255)"))
        con.execute(text("INSERT INTO paper_trades VALUES (1.1234567,10.255,0.01)"))
    try:
        outcome=report(engine)
        assert outcome["read_only"]
        assert outcome["checks"]["paper_accounts"]["cash"]["precision_loss"]==1
        assert outcome["checks"]["paper_trades"]["quantity"]["precision_loss"]==1
        assert outcome["checks"]["paper_trades"]["price"]["precision_loss"]==1
        with engine.connect() as con:
            assert con.scalar(text("SELECT COUNT(*) FROM paper_accounts"))==2
    finally:
        with engine.begin() as con:
            con.execute(text("DROP TABLE paper_trades"))
            con.execute(text("DROP TABLE paper_accounts"))
        engine.dispose()
