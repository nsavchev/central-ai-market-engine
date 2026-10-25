import pytest
from pydantic import ValidationError
from app.main import TradeRequest

@pytest.mark.parametrize("field,value", [
    ("quantity", float("nan")), ("price", float("inf")),
    ("fee", float("nan")), ("quantity", float("-inf")),
])
def test_nonfinite_fill_denied(field, value):
    data=dict(symbol="SPY", side="BUY", quantity=1, price=100, fee=0)
    data[field]=value
    with pytest.raises(ValidationError):
        TradeRequest(**data)

@pytest.mark.parametrize("field,value", [
    ("price", 100.001), ("fee", 0.001),
    ("quantity", 0.1234567), ("price", 1000001),
])
def test_overprecision_or_limit_denied(field, value):
    data=dict(symbol="SPY", side="BUY", quantity=1, price=100, fee=0)
    data[field]=value
    with pytest.raises(ValidationError):
        TradeRequest(**data)

def test_valid_manual_fill():
    trade=TradeRequest(symbol="SPY", side="BUY", quantity=0.123456, price=100.01, fee=0.02)
    assert trade.price == 100.01
