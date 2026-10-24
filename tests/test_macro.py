from datetime import datetime,timezone
import pytest
from pydantic import ValidationError
from app.macro import Event,evaluate
BASE={"event_id":"x","indicator":"CPI_YOY","country":"US","released_at":"2026-09-15T12:30:00+00:00","actual":3.2,"consensus":3.0,"unit":"percent_yoy","source_url":"https://example.org/demo","historical_surprise_std":0.2}
ASOF=datetime(2026,10,18,tzinfo=timezone.utc)
def test_surprise():
    r=evaluate([Event(**BASE)],ASOF)["events"][0]
    assert r["surprise"]==0.2 and r["standardized_surprise"]==1 and r["simple_directional_hint"]=="unfavorable"
def test_missing_consensus_no_score():
    r=evaluate([Event(**{**BASE,"consensus":None})],ASOF)["events"][0]
    assert r["priority_score"] is None
def test_future_release_no_actual_leak():
    r=evaluate([Event(**{**BASE,"released_at":"2026-11-01T00:00:00+00:00"})],ASOF)["events"][0]
    assert r["status"]=="upcoming" and r["actual"] is None
def test_consensus_after_release_rejected():
    with pytest.raises(ValidationError): Event(**{**BASE,"consensus_asof":"2026-09-16T00:00:00+00:00"})
def test_duplicate_rejected():
    e=Event(**BASE)
    with pytest.raises(ValueError): evaluate([e,e],ASOF)
