from sqlalchemy import create_engine
from app.paper_migration_baseline import inspect_legacy_baseline

def test_non_postgres_fails_closed_without_db_changes():
    e=create_engine("sqlite:///:memory:")
    assert inspect_legacy_baseline(e)=={"baseline_eligible":False,"errors":["POSTGRES_REQUIRED"]}
    e.dispose()

def test_baseline_declares_all_five_existing_tables():
    from app.paper_migration_baseline import REQUIRED, FLOAT_PAPER
    assert len(REQUIRED)==5
    assert len(FLOAT_PAPER)==4
    assert all(t in REQUIRED for t,c in FLOAT_PAPER)
