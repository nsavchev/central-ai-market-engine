from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from app import main

def request():
    return main.TradeRequest(symbol="SPY",side="BUY",quantity=1,price=40)

@pytest.mark.parametrize("legacy,v2",[
    ("NO",None),("no",None),("",None),("YES","YES"),("NO","YES")
])
def test_legacy_refused_before_database_access(monkeypatch,legacy,v2):
    monkeypatch.setenv("PAPER_LEGACY_WRITES_ENABLED",legacy)
    if v2 is None: monkeypatch.delenv("PAPER_V2_ENABLED",raising=False)
    else: monkeypatch.setenv("PAPER_V2_ENABLED",v2)
    forbidden=MagicMock(side_effect=AssertionError("DATABASE_MUST_NOT_BE_TOUCHED"))
    monkeypatch.setattr(main,"SessionLocal",forbidden)
    with pytest.raises(HTTPException) as error:
        main.paper_trade(request())
    assert error.value.status_code==409
    forbidden.assert_not_called()

def test_legacy_default_denied_without_database_access(monkeypatch):
    monkeypatch.delenv("PAPER_LEGACY_WRITES_ENABLED",raising=False)
    monkeypatch.delenv("PAPER_V2_ENABLED",raising=False)
    forbidden=MagicMock(side_effect=AssertionError("DATABASE_MUST_NOT_BE_TOUCHED"))
    monkeypatch.setattr(main,"SessionLocal",forbidden)
    with pytest.raises(HTTPException) as error:
        main.paper_trade(request())
    assert error.value.status_code==409
    forbidden.assert_not_called()

def test_legacy_explicit_opt_in_reaches_legacy_path(monkeypatch):
    monkeypatch.setenv("PAPER_LEGACY_WRITES_ENABLED","YES")
    monkeypatch.delenv("PAPER_V2_ENABLED",raising=False)
    marker=RuntimeError("REACHED_LEGACY_DATABASE_PATH")
    monkeypatch.setattr(main.SessionLocal,"begin",MagicMock(side_effect=marker))
    with pytest.raises(RuntimeError,match="REACHED_LEGACY_DATABASE_PATH"):
        main.paper_trade(request())


@pytest.mark.parametrize('field,value', [
    ('quantity', float('inf')), ('price', float('inf')), ('fee', float('inf')),
    ('quantity', float('nan')), ('price', float('nan')), ('fee', float('nan')),
    ('quantity', float('-inf')), ('price', float('-inf')), ('fee', float('-inf')),
    ('price', 100.001), ('fee', 0.001), ('quantity', 0.1234567),
    ('quantity', 1_000_001), ('price', 1_000_001), ('fee', 1_000_001),
])
def test_legacy_fill_rejects_unsafe_numeric_inputs(field, value):
    from pydantic import ValidationError

    data = dict(symbol='SPY', side='BUY', quantity=1, price=100, fee=0)
    data[field] = value
    with pytest.raises(ValidationError):
        main.TradeRequest(**data)


def test_legacy_fill_accepts_documented_numeric_boundaries():
    trade = main.TradeRequest(symbol='SPY', side='BUY', quantity=0.123456, price=100.01, fee=0.02)
    assert trade.quantity == 0.123456 and trade.price == 100.01 and trade.fee == 0.02
    trade = main.TradeRequest(symbol='SPY', side='BUY', quantity=1_000_000, price=1_000_000, fee=1_000_000)
    assert trade.quantity == trade.price == trade.fee == 1_000_000
