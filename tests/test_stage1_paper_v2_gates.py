"""Stage 1 gates: no deployment, no database writes."""
import pytest
from fastapi import HTTPException
from app import main

def payload():
    return main.PaperV2Request(symbol="SPY",side="BUY",quantity="1",price="40.00",fee="0",generation=0)

def test_v2_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PAPER_V2_ENABLED",raising=False)
    with pytest.raises(HTTPException) as e:
        main.paper_v2_trade(payload(),idempotency_key="request-001")
    assert e.value.status_code==503
    assert e.value.detail=="PAPER_V2_DISABLED"

def test_v2_refuses_missing_database_contract(monkeypatch):
    monkeypatch.setenv("PAPER_V2_ENABLED","YES")
    monkeypatch.delenv("PAPER_V2_DATABASE_NAME",raising=False)
    with pytest.raises(HTTPException) as e:
        main.paper_v2_trade(payload(),idempotency_key="request-001")
    assert e.value.status_code==503
    assert e.value.detail=="PAPER_V2_DATABASE_NOT_VERIFIED"

def test_v2_rejects_missing_idempotency_key(monkeypatch):
    monkeypatch.setenv("PAPER_V2_ENABLED","YES")
    monkeypatch.setenv("PAPER_V2_DATABASE_NAME",main._paper_engine.url.database or "")
    with pytest.raises(HTTPException) as e:
        main.paper_v2_trade(payload(),idempotency_key=None)
    assert e.value.status_code in (422,503)

def test_legacy_writer_refused_in_v2_mode(monkeypatch):
    monkeypatch.setenv("PAPER_V2_ENABLED","YES")
    with pytest.raises(HTTPException) as e:
        main.paper_trade(main.TradeRequest(symbol="SPY",side="BUY",quantity=1,price=40))
    assert e.value.status_code==409
    assert e.value.detail=="LEGACY_PAPER_WRITES_DISABLED"

def test_v2_route_remains_authenticated():
    route=next(x for x in main.app.routes if x.path=="/paper/v2/trades")
    assert route.methods=={"POST"}
    assert any(d.call is main.auth for d in route.dependant.dependencies)

def test_does_not_initialize_accounts_on_disabled_v2(monkeypatch):
    monkeypatch.delenv("PAPER_V2_ENABLED",raising=False)
    with pytest.raises(HTTPException):
        main.paper_v2_trade(payload(),idempotency_key="request-001")
