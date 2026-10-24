import pytest
from pydantic import ValidationError
from app.valuation import ValuationRequest, Scenario, evaluate

def sample(**kw):
    d=dict(symbol='TEST',base_fcff=100,net_debt=0,diluted_shares=10,current_price=10,price_asof='2026-10-18',scenarios=[dict(name='base',growth_rate=0,discount_rate=.10,terminal_growth_rate=0,years=5)])
    d.update(kw)
    return ValuationRequest.model_validate(d)

def test_constant_cashflow_perpetuity():
    r=evaluate(sample())['scenarios'][0]
    assert r['enterprise_value']==pytest.approx(1000,abs=.01)
    assert r['fair_value_per_share']==pytest.approx(100,abs=.001)

def test_net_debt_reduces_equity():
    assert evaluate(sample(net_debt=200))['scenarios'][0]['fair_value_per_share']==pytest.approx(80)

def test_terminal_spread_rejected():
    with pytest.raises(ValidationError): Scenario(name='bad',growth_rate=0,discount_rate=.02,terminal_growth_rate=.03)

def test_negative_equity_no_invalid_cagr():
    r=evaluate(sample(net_debt=2000))['scenarios'][0]
    assert r['implied_annual_price_cagr_pct'] is None
    assert r['margin_of_safety_pct'] is None

def test_exit_multiple():
    r=evaluate(sample(scenarios=[dict(name='base',growth_rate=0,discount_rate=.1,terminal_growth_rate=0,years=5,terminal_multiple=10)]))['scenarios'][0]
    assert r['terminal_method']=='EXIT_FCFF_MULTIPLE'

def test_sensitivity_matrix_and_invalid_cells():
    r=evaluate(sample(scenarios=[dict(name='base',growth_rate=0,discount_rate=.02,terminal_growth_rate=.015,years=5)]))
    assert len(r['sensitivity'])==3
    assert r['sensitivity'][0]['values'][0]['fair_value_per_share'] is None

def test_duplicate_names_rejected():
    with pytest.raises(ValidationError): sample(scenarios=[dict(name='base',growth_rate=0,discount_rate=.1,terminal_growth_rate=0),dict(name='base',growth_rate=0,discount_rate=.1,terminal_growth_rate=0)])
