import json
import pytest
from central_ai.worker_supervised import run_supervised

def test_disabled(tmp_path):
    db=tmp_path/"tasks.sqlite";db.touch()
    with pytest.raises(ValueError,match="SERVICE_DISABLED"):
        run_supervised(enabled="",database=str(db),agent="ci",lock_path=str(tmp_path/"run.lock"),status_path=str(tmp_path/"status.json"))

def test_status_on_success(tmp_path):
    db=tmp_path/"tasks.sqlite";db.touch()
    status=tmp_path/"status.json"
    result=run_supervised(enabled="YES",database=str(db),agent="ci",lock_path=str(tmp_path/"run.lock"),status_path=str(status),
        scheduler=lambda **kwargs:{"status":"complete","cycles":2,"processed":3})
    assert result["processed"]==3
    state=json.loads(status.read_text())
    assert state["state"]=="complete" and state["processed"]==3

def test_status_on_failure(tmp_path):
    db=tmp_path/"tasks.sqlite";db.touch()
    status=tmp_path/"status.json"
    def fail(**kwargs): raise RuntimeError("private-detail-must-not-leak")
    with pytest.raises(RuntimeError):
        run_supervised(enabled="YES",database=str(db),agent="ci",lock_path=str(tmp_path/"run.lock"),status_path=str(status),scheduler=fail)
    state=json.loads(status.read_text())
    assert state["state"]=="failed" and state["error_type"]=="RuntimeError"
    assert "private-detail" not in status.read_text()
