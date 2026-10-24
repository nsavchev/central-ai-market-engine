import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base, FinancialSnapshot
from app.fundamentals import Financials
from app.fundamentals_history import store_snapshot, history_report, annual_cagr

@pytest.fixture
def db():
    eng=create_engine('sqlite://')
    Base.metadata.create_all(eng)
    with Session(eng) as session: yield session
    eng.dispose()

def sample(year, revenue=100):
    return Financials(symbol='DEMO',period_end=f'{year}-12-31',period_type='FY',currency='USD',source='manual',revenue=revenue,net_income=10,operating_income=15,invested_capital=60,income_tax=2,pretax_income=12,total_debt=20,cash=5,shareholders_equity=50,operating_cash_flow=20,capital_expenditure=5)

def test_cagr():
    assert annual_cagr(100,121,2)==10
    assert annual_cagr(-100,121,2) is None

def test_store_and_report(db):
    store_snapshot(db,sample(2023,100));store_snapshot(db,sample(2024,110));store_snapshot(db,sample(2025,121));db.commit()
    r=history_report(db,'DEMO','USD','manual')
    assert r['records']==3
    assert r['trends']['revenue_cagr_pct']==pytest.approx(10,abs=.02)
    assert r['financial_health']['debt_to_equity']==.4

def test_idempotent_import(db):
    store_snapshot(db,sample(2024,100));store_snapshot(db,sample(2024,200));db.commit()
    assert db.query(FinancialSnapshot).count()==1
    assert history_report(db,'DEMO','USD','manual')['records']==1

def test_reject_unapproved_source(db):
    with pytest.raises(PermissionError): store_snapshot(db,sample(2024).model_copy(update={'source':'investolens'}))

def test_missing_year_warning(db):
    store_snapshot(db,sample(2021));store_snapshot(db,sample(2025));db.commit()
    assert any('Missing fiscal years' in x for x in history_report(db,'DEMO','USD','manual')['warnings'])
