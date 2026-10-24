import pytest
from pydantic import ValidationError
from app.advanced_valuation import AdvancedRequest,analyze,value

def req():
    return AdvancedRequest(symbol="T",normalized_fcff=100,net_debt=0,diluted_shares=10,price=100,price_asof="2026-10-18",cases=[
        dict(name="bear",probability=.25,growth_first_five=0,growth_next_five=0,discount_rate=.1,terminal_growth=0),
        dict(name="base",probability=.5,growth_first_five=0,growth_next_five=0,discount_rate=.1,terminal_growth=0),
        dict(name="bull",probability=.25,growth_first_five=0,growth_next_five=0,discount_rate=.1,terminal_growth=0)])

def test_constant_perpetuity():
    r=analyze(req())
    assert r["probability_weighted_fair_value"]==pytest.approx(100,abs=.001)
    assert r["weighted_buy_below"]==pytest.approx(75)

def test_reverse_dcf_zero_growth():
    assert abs(analyze(req())["reverse_dcf_base_case"]["required_growth"])<1e-4

def test_net_debt_subtracted():
    r=req().model_copy(update={"net_debt":100})
    assert analyze(r)["probability_weighted_fair_value"]==pytest.approx(90)

def test_probabilities_validated():
    data=req().model_dump();data["cases"][0]["probability"]=.5
    with pytest.raises(ValidationError):AdvancedRequest.model_validate(data)

def test_spread_validated():
    data=req().model_dump();data["cases"][0]["terminal_growth"]=.1
    with pytest.raises(ValidationError):AdvancedRequest.model_validate(data)

def test_upside_and_weights():
    data=req().model_dump();data["cases"][2]["growth_first_five"]=.1
    r=analyze(AdvancedRequest.model_validate(data))
    assert r["probability_weighted_fair_value"]>100
    assert r["cases"][2]["fair_value"]>r["cases"][0]["fair_value"]
