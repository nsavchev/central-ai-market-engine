import os
import pytest
from sqlalchemy import create_engine,text
from app.paper_account_bootstrap import bootstrap_paper_account

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL only")

@pytest.fixture
def engine():
    assert URL and URL.endswith("/test"), "Only disposable CI PostgreSQL test database"
    db=create_engine(URL)
    with db.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS paper_accounts"))
        c.execute(text("CREATE TABLE paper_accounts(id integer primary key,cash numeric(20,2),currency varchar(8))"))
    yield db
    with db.begin() as c:
        c.execute(text("DROP TABLE paper_accounts"))
    db.dispose()

def test_creates_once_and_does_not_reset_balance(engine):
    created=bootstrap_paper_account(engine)
    assert created["initial_cash"]=="100000.00"
    with pytest.raises(ValueError,match="ACCOUNT_ALREADY_EXISTS"):
        bootstrap_paper_account(engine)
    with engine.connect() as c:
        assert str(c.scalar(text("SELECT cash FROM paper_accounts WHERE id=1")))=="100000.00"

def test_invalid_seed_rejected(engine):
    for amount in ("NaN","-1","0","1.001"):
        with pytest.raises(ValueError):
            bootstrap_paper_account(engine,initial_cash=amount)
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM paper_accounts"))==0

def test_wrong_schema_rejected(engine):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE paper_accounts ALTER COLUMN cash TYPE double precision"))
    with pytest.raises(ValueError,match="NUMERIC_ACCOUNT_SCHEMA_REQUIRED"):
        bootstrap_paper_account(engine)
