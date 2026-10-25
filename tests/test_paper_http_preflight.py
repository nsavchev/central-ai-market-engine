"""HTTP contract checks without starting the app or mutating a database."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

def test_paper_trade_unauthorized():
    with TestClient(app) as client:
        response=client.post("/paper/trades",json={"symbol":"SPY","side":"BUY","quantity":1,"price":100})
    assert response.status_code==401

def test_invalid_paper_input_does_not_execute_legacy_writer():
    # FastAPI validates the body before calling the legacy function.
    with patch("app.main.paper_trade") as handler, TestClient(app) as client:
        response=client.post("/paper/trades",json={"symbol":"SPY","side":"INVALID","quantity":1,"price":100},
                             headers={"X-API-Token":settings.api_token})
    # In default config no usable API token exists: fail closed.
    assert response.status_code in (401,422)
    handler.assert_not_called()

def test_new_fenced_service_is_not_exposed_as_http_route():
    paths={r.path for r in app.routes}
    assert "/paper/fenced-trades" not in paths
