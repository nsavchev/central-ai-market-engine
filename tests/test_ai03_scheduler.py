import fcntl
import pytest
from central_ai.worker_scheduler import scheduled_cycles

def test_default_deny(tmp_path):
    db=tmp_path/"tasks.sqlite"
    db.touch()
    with pytest.raises(ValueError, match="SCHEDULER_DISABLED"):
        scheduled_cycles(enabled="",database=str(db),agent="test",lock_path=str(tmp_path/"worker.lock"))

def test_bounded_cycles(tmp_path):
    db=tmp_path/"tasks.sqlite"
    db.touch()
    calls=[]
    def batch(**kwargs):
        calls.append(kwargs)
        return {"processed":2}
    result=scheduled_cycles(enabled="YES", database=str(db),agent="test",lock_path=str(tmp_path/"worker.lock"),cycles=3,interval=1,sleep=lambda _:None,batch=batch)
    assert result=={"status":"complete","cycles":3,"processed":6}
    assert len(calls)==3

def test_single_instance_lock(tmp_path):
    db=tmp_path/"tasks.sqlite"
    db.touch()
    path=tmp_path/"worker.lock"
    with path.open("a+") as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=scheduled_cycles(enabled="YES",database=str(db),agent="test",lock_path=str(path),cycles=1,batch=lambda **kwargs:{"processed":1})
        assert result["status"]=="already_running"

def test_invalid_limits(tmp_path):
    db=tmp_path/"tasks.sqlite"
    db.touch()
    with pytest.raises(ValueError,match="INVALID_CYCLES"):
        scheduled_cycles(enabled="YES",database=str(db),agent="test",lock_path=str(tmp_path/"worker.lock"),cycles=0)
