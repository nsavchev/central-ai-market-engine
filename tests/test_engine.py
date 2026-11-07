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


def test_http_ibkr_failure_redacts_client_and_log_details(market_api, monkeypatch, caplog):
    import re
    from unittest.mock import MagicMock

    request, _ = market_api
    private_detail = 'broker password=synthetic-secret; account=private-account\nprivate-path'
    monkeypatch.setattr(main, 'fetch_daily', MagicMock(side_effect=RuntimeError(private_detail)))
    database = MagicMock()
    monkeypatch.setattr(main, 'SessionLocal', database)

    response = request('POST', '/ingest/ibkr', json={'symbol': 'SPY'})
    assert response.status_code == 502
    detail = response.json()['detail']
    assert detail['code'] == 'IBKR_INGEST_FAILED'
    assert re.fullmatch(r'[0-9a-f]{24}', detail['error_id'])
    assert private_detail not in response.text
    assert 'synthetic-secret' not in caplog.text
    assert 'private-account' not in caplog.text
    assert 'private-path' not in caplog.text
    assert f"IBKR_INGEST_FAILED id={detail['error_id']}" in caplog.text
    database.begin.assert_not_called()


def test_http_ibkr_errors_have_distinct_correlation_ids(market_api, monkeypatch):
    from unittest.mock import MagicMock

    request, _ = market_api
    monkeypatch.setattr(main, 'fetch_daily', MagicMock(side_effect=RuntimeError('synthetic failure')))
    responses = [request('POST', '/ingest/ibkr', json={'symbol': 'SPY'}) for _ in range(2)]
    assert all(response.status_code == 502 for response in responses)
    ids = [response.json()['detail']['error_id'] for response in responses]
    assert ids[0] != ids[1]


def test_http_ibkr_success_preserves_import_and_update(market_api, monkeypatch):
    request, sessions = market_api
    bar = {'day': '2026-10-30', 'open': 100, 'high': 102,
           'low': 99, 'close': 101, 'volume': 1000}
    monkeypatch.setattr(main, 'fetch_daily', lambda *args: [bar])
    for close in (101, 102):
        bar['close'] = close
        response = request('POST', '/ingest/ibkr', json={'symbol': 'SPY'})
        assert response.status_code == 200, response.text
        assert response.json() == {'symbol': 'SPY', 'bars_received': 1}
    with sessions() as db:
        assert db.query(Instrument).count() == 1
        rows = db.query(DailyBar).all()
        assert len(rows) == 1 and rows[0].close == 102


@pytest.mark.parametrize('field,value', [
    ('quantity', 'Infinity'), ('price', 'Infinity'), ('fee', 'Infinity'),
    ('price', 100.001), ('fee', 0.001), ('quantity', 0.1234567),
])
def test_http_legacy_fill_rejects_unsafe_values_before_ledger_access(market_api, monkeypatch, field, value):
    from unittest.mock import MagicMock

    request, _ = market_api
    monkeypatch.setenv('PAPER_LEGACY_WRITES_ENABLED', 'YES')
    monkeypatch.delenv('PAPER_V2_ENABLED', raising=False)
    database = MagicMock()
    monkeypatch.setattr(main, 'SessionLocal', database)
    data = dict(symbol='SPY', side='SELL', quantity=1, price=100, fee=0)
    data[field] = value
    response = request('POST', '/paper/trades', json=data)
    assert response.status_code == 422, response.text
    database.begin.assert_not_called()


def financial_history_payload(**changes):
    payload = dict(symbol='DEMO', period_end='2025-12-31', period_type='FY',
                   currency='USD', source='manual', units='ones',
                   total_assets='100', total_liabilities='40', shareholders_equity='60',
                   revenue='100.125')
    payload.update(changes)
    return payload


def test_http_financial_history_preserves_metadata_and_idempotent_identity(market_api):
    from app.db import FinancialSnapshot
    request, sessions = market_api
    payload = financial_history_payload()
    for revenue in ('100.125', '200.25'):
        payload['revenue'] = revenue
        response = request('POST', '/fundamentals/history/import', json=[payload])
        assert response.status_code == 200, response.text
    with sessions() as db:
        row = db.query(FinancialSnapshot).one()
        assert row.payload['units'] == 'ones' and row.payload['total_liabilities'] == '40'
        assert row.payload['revenue'] == '200.25'
    report = request('GET', '/fundamentals/history/DEMO')
    assert report.status_code == 200, report.text
    assert report.json()['records'] == 1 and report.json()['units'] == 'ones'
    assert any('MISSING_RETRIEVAL_TIME' in warning for warning in report.json()['warnings'])


@pytest.mark.parametrize('changes', [
    {'units': None}, {'total_liabilities': 20}, {'period_end': '2099-12-31'},
    {'units': 'millions'}, {'source': 'investolens'}, {'source': 'sec_edgar'},
])
def test_http_financial_history_rejects_invalid_inputs_without_rows(market_api, changes):
    from app.db import FinancialSnapshot
    request, sessions = market_api
    response = request('POST', '/fundamentals/history/import',
                       json=[financial_history_payload(**changes)])
    assert response.status_code == 422, response.text
    with sessions() as db:
        assert db.query(FinancialSnapshot).count() == 0


def test_http_financial_history_batch_is_atomic_on_quality_rejection(market_api):
    from app.db import FinancialSnapshot
    request, sessions = market_api
    response = request('POST', '/fundamentals/history/import', json=[
        financial_history_payload(),
        financial_history_payload(period_end='2024-12-31', units=None),
    ])
    assert response.status_code == 422 and 'UNITS_UNCONFIRMED' in response.json()['detail']
    with sessions() as db:
        assert db.query(FinancialSnapshot).count() == 0


def test_http_legacy_history_refusal_does_not_infer_or_rewrite_units(market_api):
    from app.db import FinancialSnapshot
    request, sessions = market_api
    payload = financial_history_payload()
    payload.pop('units')
    with sessions.begin() as db:
        db.add(FinancialSnapshot(symbol='DEMO', period_end=date(2025, 12, 31),
                                period_type='FY', currency='USD', source='manual', payload=payload))
    response = request('GET', '/fundamentals/history/DEMO')
    assert response.status_code == 422 and 'UNITS_UNCONFIRMED' in response.json()['detail']
    with sessions() as db:
        assert db.query(FinancialSnapshot).one().payload == payload


def test_http_financial_history_requires_auth_before_database_access(market_api, monkeypatch):
    from unittest.mock import MagicMock
    request, _ = market_api
    database = MagicMock()
    monkeypatch.setattr(main, 'SessionLocal', database)
    response = request('POST', '/fundamentals/history/import', headers={},
                       json=[financial_history_payload()])
    assert response.status_code == 401
    assert not database.mock_calls
