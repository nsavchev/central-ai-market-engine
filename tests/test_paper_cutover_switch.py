import pytest
from app.paper_cutover_switch import Phase, Evidence, transition

def test_default_refuses_quiesce():
    with pytest.raises(PermissionError,match="QUIESCE_REQUIRES_EVIDENCE"):
        transition(Phase.LEGACY,Phase.QUIESCED,Evidence())

def test_requires_full_evidence_for_numeric():
    proof=Evidence(backup_restored=True,legacy_writers_stopped=True)
    assert transition(Phase.LEGACY,Phase.QUIESCED,proof)==Phase.QUIESCED
    with pytest.raises(PermissionError,match="CUTOVER_NOT_AUTHORIZED"):
        transition(Phase.QUIESCED,Phase.NUMERIC_READY,proof)

def test_explicit_reviewed_transition():
    proof=Evidence(True,True,True,True,True,True)
    assert transition(Phase.QUIESCED,Phase.NUMERIC_READY,proof)==Phase.NUMERIC_READY

def test_invalid_reverse_transition_refused():
    with pytest.raises(PermissionError,match="INVALID_PHASE_TRANSITION"):
        transition(Phase.NUMERIC_READY,Phase.LEGACY,Evidence(True,True,True,True,True,True))
