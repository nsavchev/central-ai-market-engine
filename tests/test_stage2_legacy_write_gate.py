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

def test_legacy_default_retained_for_old_deployment(monkeypatch):
    monkeypatch.delenv("PAPER_LEGACY_WRITES_ENABLED",raising=False)
    monkeypatch.delenv("PAPER_V2_ENABLED",raising=False)
    # This is a compatibility gate check, not a real write.
    marker=RuntimeError("REACHED_LEGACY_DATABASE_PATH")
    monkeypatch.setattr(main,"SessionLocal",MagicMock(side_effect=marker))
    with pytest.raises(RuntimeError,match="REACHED_LEGACY_DATABASE_PATH"):
        main.paper_trade(request())
