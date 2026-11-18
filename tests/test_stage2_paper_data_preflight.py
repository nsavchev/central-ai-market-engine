import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DataError

from app.paper_data_preflight import _fits

def test_exactly_representable_values():
    assert _fits(100000.0,20,2)
    assert _fits("1.000001",24,6)
    assert _fits("0.01",20,2)
    # NUMERIC(20,2) permits 18 integer digits and two fractional digits.
    # https://www.postgresql.org/docs/16/datatype-numeric.html
    assert _fits("999999999999999999.99",20,2)
    assert _fits("-999999999999999999.99",20,2)

def test_fractional_precision_loss_rejected():
    assert not _fits("1.001",20,2)
    assert not _fits("0.0000001",24,6)

def test_invalid_values_rejected():
    assert not _fits("NaN",20,2)
    assert not _fits("Infinity",20,2)
    assert not _fits("1000000000000000000.00",20,2)
    assert not _fits("-1000000000000000000.00",20,2)


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL") and not os.getenv("CI"),
                    reason="Disposable PostgreSQL required for local execution")
@pytest.mark.parametrize("value,fits", [
    ("999999999999999999.99", True),
    ("-999999999999999999.99", True),
    ("1000000000000000000.00", False),
    ("-1000000000000000000.00", False),
])
def test_cash_boundaries_agree_with_real_postgres(value, fits):
    url = make_url(os.environ["TEST_POSTGRES_URL"])
    assert url.host in ("localhost", "127.0.0.1") and url.database == "test"
    engine = create_engine(url)
    try:
        assert _fits(value, 20, 2) is fits
        with engine.connect() as con:
            if fits:
                assert con.scalar(text("SELECT CAST(:value AS numeric(20,2))"),
                                  {"value": value}) == Decimal(value)
            else:
                with pytest.raises(DataError) as error:
                    con.scalar(text("SELECT CAST(:value AS numeric(20,2))"), {"value": value})
                assert error.value.orig.sqlstate == "22003"
    finally:
        engine.dispose()
