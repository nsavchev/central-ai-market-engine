from app.paper_precision_audit import assess

def test_exact_cents():
    assert assess(100.25,integer_digits=18,decimal_places=2)["safe"]

def test_fractional_cent_blocked():
    assert assess(100.255,integer_digits=18,decimal_places=2)["reason"]=="PRECISION_LOSS"

def test_quantity_precision_blocked():
    assert assess(0.1234567,integer_digits=18,decimal_places=6)["reason"]=="PRECISION_LOSS"

def test_nonfinite_blocked():
    assert assess(float("nan"),integer_digits=18,decimal_places=2)["reason"]=="NONFINITE"

def test_overflow_blocked():
    assert assess(1e20,integer_digits=18,decimal_places=2)["reason"]=="OUT_OF_RANGE"

def test_null_blocked():
    assert assess(None,integer_digits=18,decimal_places=2)["reason"]=="NULL_OR_BOOLEAN"
