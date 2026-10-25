import sqlite3
import pytest
from app.paper_write_fence import PaperWriteFence

def test_fence_survives_restart(tmp_path):
    path=str(tmp_path/"fence.sqlite")
    f=PaperWriteFence(path)
    f.initialize()
    assert f.read()=={"mode":"LEGACY","generation":0}
    with pytest.raises(PermissionError,match="APPROVAL_REQUIRED"):
        f.quiesce(expected_generation=0)
    assert f.quiesce(expected_generation=0,manual_approval=True)["generation"]==1
    assert PaperWriteFence(path).read()["mode"]=="QUIESCED"

def test_old_generation_rejected(tmp_path):
    path=str(tmp_path/"fence.sqlite")
    f=PaperWriteFence(path);f.initialize()
    f.quiesce(expected_generation=0,manual_approval=True)
    with sqlite3.connect(path) as db:
        with pytest.raises(PermissionError,match="PAPER_WRITES_FENCED"):
            f.check_write_allowed(db,generation=0)
    with pytest.raises(PermissionError,match="STALE_GENERATION"):
        f.quiesce(expected_generation=0,manual_approval=True)

def test_missing_fence_fails_closed(tmp_path):
    f=PaperWriteFence(str(tmp_path/"not_initialized.sqlite"))
    with pytest.raises(sqlite3.OperationalError):
        f.read()
