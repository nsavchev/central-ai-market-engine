"""True Alembic CLI chain on disposable PostgreSQL (no VPS access)."""
import os, subprocess
from sqlalchemy import create_engine,text
def test_realistic_constraints_survive_alembic_upgrade():
    url=os.environ["TEST_POSTGRES_URL"]
    assert url.endswith("/test") and "127.0.0.1" in url
    engine=create_engine(url)
    with engine.begin() as con:
        for name in ("instruments","daily_bars","financial_snapshots","paper_accounts","paper_trades"):
            # Synthetic legacy schema: the baseline preflight checks required columns.
            cols={
              "instruments":"id int primary key,symbol text,exchange text,currency text,sec_type text,primary_exchange text, UNIQUE(symbol,exchange,currency,sec_type,primary_exchange)",
              "daily_bars":"id int primary key,instrument_id int REFERENCES instruments(id),day date,open double precision,high double precision,low double precision,close double precision,volume double precision,source text,fetched_at timestamptz, UNIQUE(instrument_id,day,source)",
              "financial_snapshots":"id int primary key,symbol text,period_end date,period_type text,currency text,source text,payload json,imported_at timestamptz, UNIQUE(symbol,period_end,period_type,currency,source)",
              "paper_accounts":"id int primary key,cash double precision,currency text",
              "paper_trades":"id int primary key,account_id int REFERENCES paper_accounts(id),symbol text,side text,quantity double precision,price double precision,fee double precision,executed_at timestamptz",
            }
            con.execute(text("CREATE TABLE "+name+" ("+cols[name]+")"))
        con.execute(text("INSERT INTO paper_accounts VALUES(1,1234.5,'USD')"))
        con.execute(text("INSERT INTO paper_trades VALUES(1,1,'SPY','BUY',2.0,55.25,0.5,NULL)"))
    subprocess.run(["alembic","-c","alembic-stage2.ini","upgrade","head"],check=True,
                   env={**os.environ,"STAGE2_DISPOSABLE_DB":"YES"})
    with engine.connect() as con:
        assert con.scalar(text("SELECT version_num FROM alembic_version"))=="stage2_numeric_002"
        assert con.scalar(text("SELECT mode FROM paper_write_fence WHERE id=1"))=="QUIESCED"
        assert con.scalar(text("SELECT generation FROM paper_write_fence WHERE id=1"))==1
        assert str(con.scalar(text("SELECT cash FROM paper_accounts WHERE id=1")))=="1234.50"
        assert str(con.scalar(text("SELECT price FROM paper_trades WHERE id=1")))=="55.25"
        types=con.execute(text("""SELECT column_name,numeric_precision,numeric_scale FROM information_schema.columns
            WHERE table_name='paper_trades' AND column_name IN ('quantity','price','fee')""")).all()
        assert {(r[0],r[1],r[2]) for r in types}=={("quantity",24,6),("price",20,2),("fee",20,2)}
    from app.paper_schema_constraints import inspect_relational_constraints
    assert inspect_relational_constraints(engine)=={"ready":True,"errors":[]}
    engine.dispose()
