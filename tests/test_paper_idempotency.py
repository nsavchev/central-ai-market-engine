import pytest
from app.paper_idempotency import request_fingerprint,idempotent_fill

def test_identical_canonical_payload_fingerprint():
    a=dict(account_id=1,symbol="SPY",side="BUY",quantity="1",price="40",fee="0",generation=0)
    b={**a,"quantity":"1.000000","price":"40.00","fee":"0.00"}
    assert request_fingerprint(**a)==request_fingerprint(**b)

def test_invalid_numeric_input_refused():
    with pytest.raises(ValueError):
        request_fingerprint(account_id=1,symbol="SPY",side="BUY",quantity="NaN",
                            price="40",fee="0",generation=0)
