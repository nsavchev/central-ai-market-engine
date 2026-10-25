import os
import pytest
from sqlalchemy import create_engine,text
from app.paper_cutover_compat import assess

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL required")

@pytest.fixture
def engine():
    eng=create_engine(URL)
    with eng.begin() as con:
        con.execute(text("DROP TABLE IF EXISTS paper_trades"))
        con.execute(text("DROP TABLE IF EXISTS paper_accounts"))
        con.execute(text("CREATE TABLE paper_accounts(id int PRIMARY KEY,cash double precision,cash_numeric numeric(20,2))"))
        con.execute(text("""CREATE TABLE paper_trades (
            id int PRIMARY KEY,quantity double precision,price double precision,fee double precision,
            quantity_numeric numeric(24,6),price_numeric numeric(20,2),fee_numeric numeric(20,2))"""))
    yield eng
    with eng.begin() as con:
        con.execute(text("DROP TABLE paper_trades"))
        con.execute(text("DROP TABLE paper_accounts"))
    eng.dispose()

def test_shadow_columns_do_not_satisfy_service_contract(engine):
    result=assess(engine)
    assert not result["ready_for_atomic_service"]
    assert len(result["blockers"])==4
    assert len(result["shadow_fields_present"])==4

def test_numeric_canonical_columns_satisfy_structural_only_check(engine):
    with engine.begin() as con:
        con.execute(text("ALTER TABLE paper_accounts ALTER COLUMN cash TYPE NUMERIC(20,2)"))
        for field,scale in (("quantity",6),("price",2),("fee",2)):
            con.execute(text(f"ALTER TABLE paper_trades ALTER COLUMN {field} TYPE NUMERIC(24,{scale})"))
    result=assess(engine)
    assert result["ready_for_atomic_service"]
    assert not result["blockers"]
