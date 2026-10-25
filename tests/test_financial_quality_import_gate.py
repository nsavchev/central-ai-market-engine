import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import Base, FinancialSnapshot
from app.fundamentals import Financials
from app.fundamentals_history import store_snapshot

def item(**changes):
    data=dict(symbol="DEMO",period_end="2025-12-31",period_type="FY",
              currency="USD",source="manual",units="ones",
              accounting_standard="US_GAAP",retrieved_at="2026-10-25T00:00:00Z",
              revenue=100,total_assets=100,total_liabilities=40,
              shareholders_equity=60)
    data.update(changes)
    return Financials(**data)

@pytest.fixture
def db():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()

def test_valid_snapshot_persists(db):
    store_snapshot(db,item())
    db.commit()
    assert db.scalar(select(FinancialSnapshot)).payload["units"]=="ones"

def test_missing_units_blocked(db):
    with pytest.raises(ValueError,match="UNITS_UNCONFIRMED"):
        store_snapshot(db,item(units=None))
    assert db.scalar(select(FinancialSnapshot)) is None

def test_balance_mismatch_blocked(db):
    with pytest.raises(ValueError,match="BALANCE_MISMATCH"):
        store_snapshot(db,item(total_liabilities=20))
    assert db.scalar(select(FinancialSnapshot)) is None

def test_future_date_blocked(db):
    with pytest.raises(ValueError,match="FUTURE_PERIOD"):
        store_snapshot(db,item(period_end="2099-12-31"))
    assert db.scalar(select(FinancialSnapshot)) is None

def test_disallowed_source_rejected_before_quality(db):
    with pytest.raises(PermissionError):
        store_snapshot(db,item(source="investolens",units=None))
    assert db.scalar(select(FinancialSnapshot)) is None

def test_batch_rollback_on_invalid_record(db):
    with pytest.raises(ValueError,match="FINANCIAL_QUALITY_BLOCKED"):
        with db.begin():
            store_snapshot(db,item())
            store_snapshot(db,item(period_end="2024-12-31",units=None))
    assert list(db.scalars(select(FinancialSnapshot)))==[]
