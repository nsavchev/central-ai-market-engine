import pytest
from central_ai.worker_periodic import run_periodic

def test_disabled():
    with pytest.raises(ValueError,match="PERIODIC_DISABLED"):
        run_periodic(enabled="",database="",agent="",lock_path="",status_path="")

def test_bounded_periodic():
    calls=[]
    def runner(**kwargs):
        calls.append(kwargs)
        return {"status":"complete"}
    result=run_periodic(enabled="YES",database="/tmp/test.db",agent="ci",lock_path="/tmp/test.lock",status_path="/tmp/status.json",runs=3,pause=1,runner=runner,sleep=lambda _:None)
    assert result=={"state":"complete","completed":3}
    assert len(calls)==3

def test_lock_stops():
    result=run_periodic(enabled="YES",database="/tmp/test.db",agent="ci",lock_path="/tmp/test.lock",status_path="/tmp/status.json",runs=3,pause=1,runner=lambda **kwargs:{"status":"already_running"})
    assert result=={"state":"locked","completed":0}
