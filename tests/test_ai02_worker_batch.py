import pytest
from central_ai.worker_batch import run_batch

class FakeCoordinator:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = 0
    def run_once(self):
        self.calls += 1
        return next(self.results)

def test_default_deny(tmp_path):
    db = tmp_path / "test.db"
    db.touch()
    with pytest.raises(ValueError, match="WORKER_DISABLED"):
        run_batch(enabled="", database=str(db), agent="test")

def test_bounded_tasks_and_idle(tmp_path):
    db = tmp_path / "test.db"
    db.touch()
    c = FakeCoordinator([{"status":"analyzed"}, {"status":"analyzed"}])
    got = run_batch(enabled="YES", database=str(db), agent="test", max_tasks=2, coordinator=c)
    assert got["processed"] == 2 and c.calls == 2
    d = FakeCoordinator([None, None, None])
    got = run_batch(enabled="YES", database=str(db), agent="test", idle_checks=3, sleep=lambda _:None, coordinator=d)
    assert got["processed"] == 0 and d.calls == 3

def test_limits_fail_closed(tmp_path):
    db = tmp_path / "test.db"
    db.touch()
    with pytest.raises(ValueError, match="INVALID_MAX_TASKS"):
        run_batch(enabled="YES", database=str(db), agent="test", max_tasks=0)
