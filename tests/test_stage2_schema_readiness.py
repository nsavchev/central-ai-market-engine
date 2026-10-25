from sqlalchemy import create_engine
from app.paper_schema_readiness import inspect_paper_v2_schema

def test_sqlite_fails_closed_without_writing():
    engine=create_engine("sqlite:///:memory:")
    assert inspect_paper_v2_schema(engine)=={"ready":False,"errors":["POSTGRES_REQUIRED"]}
    engine.dispose()

def test_expectations_are_precise():
    from app.paper_schema_readiness import EXPECTED
    assert EXPECTED[("paper_accounts","cash")]==("numeric",20,2)
    assert EXPECTED[("paper_trades","quantity")]==("numeric",24,6)
    assert EXPECTED[("paper_trades","price")]==("numeric",20,2)
    assert EXPECTED[("paper_trades","fee")]==("numeric",20,2)
