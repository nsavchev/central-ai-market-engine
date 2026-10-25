from unittest.mock import patch
import pytest
from fastapi import HTTPException
from app.main import ImportRequest, ingest

def test_ibkr_exception_not_exposed_to_client():
    secret = "password=TOP_SECRET broker private data"
    with patch("app.main.fetch_daily", side_effect=RuntimeError(secret)):
        with pytest.raises(HTTPException) as caught:
            ingest(ImportRequest(symbol="SPY"))
    err = caught.value
    assert err.status_code == 502
    assert err.detail["code"] == "IBKR_INGEST_FAILED"
    assert len(err.detail["error_id"]) == 24
    assert secret not in repr(err.detail)

def test_each_error_has_distinct_correlation_id():
    ids = []
    with patch("app.main.fetch_daily", side_effect=RuntimeError("secret")):
        for _ in range(2):
            with pytest.raises(HTTPException) as caught:
                ingest(ImportRequest(symbol="SPY"))
            ids.append(caught.value.detail["error_id"])
    assert ids[0] != ids[1]
