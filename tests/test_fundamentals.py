import pytest
from app.sources import SOURCES, validate_source
from app.fundamentals import Financials, calculate

BASE=dict(symbol='DEMO',period_end='2025-12-31',period_type='FY',currency='USD',source='manual',revenue=1000,net_income=100,operating_income=150,income_tax=25,pretax_income=125,total_assets=800,shareholders_equity=500,total_debt=200,cash=50,operating_cash_flow=180,capital_expenditure=50,invested_capital=650,shares_diluted=100,share_price=20,dividends_per_share=0.5)

def test_metrics():
    r=calculate(Financials(**BASE))['metrics']
    assert r['net_margin_pct']==10
    assert r['roe_pct']==20
    assert r['roic_pct']==pytest.approx(18.4615)
    assert r['free_cash_flow']==130
    assert r['fcf_yield_pct']==6.5
    assert r['pe']==20
    assert r['dividend_yield_pct']==2.5

def test_missing_inputs_null_not_zero():
    r=calculate(Financials(symbol='X',period_end='2025-12-31',period_type='FY',currency='EUR'))['metrics']
    assert r['roe_pct'] is None and r['free_cash_flow'] is None

def test_negative_capex_rejected():
    with pytest.raises(ValueError): Financials(**{**BASE,'capital_expenditure':-5})

def test_zero_equity_no_division():
    r=calculate(Financials(**{**BASE,'shareholders_equity':0}))['metrics']
    assert r['roe_pct'] is None

def test_investolens_automation_blocked():
    assert not SOURCES['investolens'].can_automate()
    with pytest.raises(PermissionError): validate_source('investolens', automated=True)
    with pytest.raises(PermissionError): validate_source('investolens')

def test_unknown_source_blocked():
    with pytest.raises(ValueError): validate_source('made_up')

def test_manual_import_allowed():
    assert validate_source('manual').key=='manual'
