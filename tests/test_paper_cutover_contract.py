from app.paper_cutover_contract import CutoverEvidence, EXPECTED, SHADOW, check

def test_shadow_only_never_counts_as_canonical():
    x=CutoverEvidence({},frozenset(SHADOW))
    r=check(x)
    assert not r["ready_for_reviewed_cutover"]
    assert len([b for b in r["blockers"] if b.startswith("CANONICAL_SCHEMA")])==4

def test_schema_alone_never_authorizes_cutover():
    r=check(CutoverEvidence(EXPECTED,frozenset()))
    assert not r["ready_for_reviewed_cutover"]
    assert "MANUAL_APPROVAL" in r["blockers"]
    assert "LEGACY_WRITERS" in r["blockers"]

def test_explicit_evidence_model():
    r=check(CutoverEvidence(EXPECTED,frozenset(),True,True,True,True,True))
    assert r["ready_for_reviewed_cutover"]
