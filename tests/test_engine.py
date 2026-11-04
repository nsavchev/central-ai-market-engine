import asyncio
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.db import Base, DailyBar, Instrument
from app.engine import returns, trend, analyze

def test_relative_strength():
    days=[date(2025,1,1)+timedelta(days=i) for i in range(201)]
    a={d:100.0 for d in days}
    b={d:100.0 for d in days}
    b[days[-1]]=95.0
    r=analyze(a,b)
    assert abs(r['relative_performance_pp']['20']-5)<1e-8

def test_insufficient_data():
    assert trend([100.0]*10)=='INSUFFICIENT_DATA'
    assert returns([100.0]*10)['20'] is None

def test_date_alignment():
    d=date(2025,1,1)
    a={d+timedelta(days=i):100+i for i in range(25)}
    b={d+timedelta(days=i):100 for i in range(24)}
    r=analyze(a,b)
    assert r['as_of']==(d+timedelta(days=23)).isoformat()


# Exercise both real HTTP routes: a shared import name once redirected the
# relative-strength route to the advanced valuation function.
TEST_TOKEN = "market-route-ci-only-token"


@pytest.fixture
def market_api(monkeypatch):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    monkeypatch.setattr(main.settings, "api_token", TEST_TOKEN)

    def request(method, path, **kwargs):
        kwargs.setdefault("headers", {"X-API-Token": TEST_TOKEN})

        async def send():
            # ASGITransport does not run lifespan: only this disposable in-memory
            # database is initialized, never the app's configured database.
            transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    try:
        yield request, sessions
    finally:
        engine.dispose()


def add_history(sessions, symbol, prices):
    with sessions.begin() as db:
        instrument = Instrument(symbol=symbol)
        db.add(instrument)
        db.flush()
        for day, close in prices.items():
            db.add(DailyBar(
                instrument_id=instrument.id, day=day,
                open=close, high=close, low=close, close=close, volume=1000,
            ))


def test_http_relative_strength_and_advanced_valuation_use_their_own_algorithms(market_api):
    request, sessions = market_api
    days = [date(2025, 1, 1) + timedelta(days=i) for i in range(201)]
    add_history(sessions, "DEMO", {day: 100.0 for day in days})
    benchmark = {day: 100.0 for day in days}
    benchmark[days[-1]] = 95.0
    add_history(sessions, "SPY", benchmark)

    response = request("GET", "/analysis/DEMO?benchmark=SPY")
    assert response.status_code == 200, response.text
    analysis = response.json()
    assert analysis["symbol"] == "DEMO" and analysis["benchmark"] == "SPY"
    assert analysis["sessions"] == 201
    assert analysis["relative_performance_pp"]["20"] == pytest.approx(5.0)

    response = request("POST", "/valuation/advanced", json={
        "symbol": "DEMO", "normalized_fcff": 100, "net_debt": 0,
        "diluted_shares": 10, "price": 100, "price_asof": "2026-10-18",
        "cases": [
            {"name": name, "probability": probability, "growth_first_five": 0,
             "growth_next_five": 0, "discount_rate": 0.1, "terminal_growth": 0}
            for name, probability in (("bear", 0.25), ("base", 0.5), ("bull", 0.25))
        ],
    })
    assert response.status_code == 200, response.text
    assert response.json()["probability_weighted_fair_value"] == pytest.approx(100)
    assert response.json()["weighted_buy_below"] == pytest.approx(75)


def test_http_analysis_rejects_nonoverlapping_history(market_api):
    request, sessions = market_api
    add_history(sessions, "DEMO", {date(2025, 1, 1): 100.0})
    add_history(sessions, "SPY", {date(2025, 2, 1): 100.0})
    response = request("GET", "/analysis/DEMO")
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "No overlapping dates"


def test_http_analysis_rejects_ambiguous_symbol(market_api):
    request, sessions = market_api
    with sessions.begin() as db:
        db.add_all([Instrument(symbol="DEMO", exchange="A"),
                    Instrument(symbol="DEMO", exchange="B")])
    assert request("GET", "/analysis/DEMO").status_code == 409


@pytest.mark.parametrize("method,path", [
    ("GET", "/analysis/DEMO"), ("POST", "/valuation/advanced"),
])
def test_analysis_and_valuation_http_routes_require_auth(market_api, method, path):
    request, _ = market_api
    assert request(method, path, headers={}).status_code == 401
