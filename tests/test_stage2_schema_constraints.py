from sqlalchemy import create_engine
from app.paper_schema_constraints import inspect_relational_constraints, EXPECTED_FKS, EXPECTED_UNIQUES

def test_rejects_non_postgres():
    engine=create_engine("sqlite:///:memory:")
    assert inspect_relational_constraints(engine)=={"ready": False, "errors": ["POSTGRES_REQUIRED"]}
    engine.dispose()

def test_expected_legacy_relationships_are_declared():
    assert ("account_id","paper_accounts","id") in EXPECTED_FKS["paper_trades"]
    assert ("instrument_id","instruments","id") in EXPECTED_FKS["daily_bars"]
    assert ("instrument_id","day","source") in EXPECTED_UNIQUES["daily_bars"]
