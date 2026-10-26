from app.paper_data_preflight import _fits

def test_exactly_representable_values():
    assert _fits(100000.0,20,2)
    assert _fits("1.000001",24,6)
    assert _fits("0.01",20,2)

def test_fractional_precision_loss_rejected():
    assert not _fits("1.001",20,2)
    assert not _fits("0.0000001",24,6)

def test_invalid_values_rejected():
    assert not _fits("NaN",20,2)
    assert not _fits("Infinity",20,2)
    assert not _fits("999999999999999999.99",20,2)
