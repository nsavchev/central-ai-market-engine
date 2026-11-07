"""AI-20: exercise existing SQLite queue bounded retries across process recreation."""
from datetime import datetime, timedelta, timezone
import sqlite3
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from central_ai.developer_task_runner import DeveloperTaskRunner

from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.task_queue import TaskQueue


def test_expired_lease_cannot_retry_more_than_three_times(tmp_path):
    db = tmp_path / "tasks.sqlite"
    source = tmp_path / "workspace"
    source.mkdir()
    (source / "module.py").write_text("def source():\n    return 1\n")
    task = PersistentTaskBridge(db).submit("Inspect module.py")
    target = TaskFileTargets(db)
    target.initialize()
    target.register(task["task_id"], str(source), "module.py")
    task_id = task["task_id"]
    for attempt in range(1, 4):
        # Each acquisition reopens the queue, simulating a restarted worker.
        queue = TaskQueue(db)
        lease = queue.acquire_next("bounded-test-agent", seconds=30, require_target=True)
        assert lease is not None
        assert lease["task_id"] == task_id
        assert queue.status(task_id)["attempt_count"] == attempt
        # Simulate lease timeout without running any code.
        with sqlite3.connect(db) as con:
            con.execute("UPDATE task_queue SET lease_until=? WHERE task_id=?",
                        ((datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat(), task_id))
    reopened = TaskQueue(db)
    assert reopened.acquire_next("bounded-test-agent", seconds=30, require_target=True) is None
    status = reopened.status(task_id)
    assert status["attempt_count"] == 3
    assert status["retry_exhausted"] == 1
    assert status["effective_status"] == "failed"
    assert status["deployment_allowed"] == 0
    assert status["approved"] == 0


# Both acquisition APIs share the same durable three-lease budget. These
# fixtures only analyze local source; no candidate execution or provider calls.


def queued_source(tmp_path):
    db = tmp_path / 'tasks.sqlite'
    workspace = tmp_path / 'source'
    workspace.mkdir()
    (workspace / 'sample.py').write_text('def sample():\n    return 1\n')
    bridge = PersistentTaskBridge(db)
    task_id = bridge.submit('Synthetic local lease regression')['task_id']
    targets = TaskFileTargets(db)
    targets.initialize()
    targets.register(task_id, str(workspace), 'sample.py')
    return db, task_id, workspace


def acquire_using(queue, task_id, agent, mode):
    if mode == 'direct':
        return queue.acquire(task_id, agent)
    lease = queue.acquire_next(agent, require_target=True)
    assert lease is None or lease['task_id'] == task_id
    return None if lease is None else lease['token']


def expire(db, task_id):
    with sqlite3.connect(db) as con:
        con.execute('UPDATE task_queue SET lease_until=? WHERE task_id=?',
                    ((datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(), task_id))


@pytest.mark.parametrize('modes', [
    ('direct', 'direct', 'direct'),
    ('scheduled', 'scheduled', 'scheduled'),
    ('direct', 'scheduled', 'direct'),
    ('scheduled', 'direct', 'scheduled'),
])
def test_acquisition_apis_share_budget_across_reopened_workers(tmp_path, modes):
    db, task_id, _ = queued_source(tmp_path)
    for attempt, mode in enumerate(modes, start=1):
        queue = TaskQueue(db)
        assert acquire_using(queue, task_id, f'worker-{attempt}', mode) is not None
        assert queue.status(task_id)['attempt_count'] == attempt
        expire(db, task_id)
    reopened = TaskQueue(db)
    before = reopened.status(task_id)
    events = reopened.audit(task_id)
    assert reopened.acquire(task_id, 'direct-fourth') is None
    assert reopened.acquire_next('scheduled-fourth', require_target=True) is None
    assert reopened.status(task_id) == before
    assert reopened.audit(task_id) == events
    assert before['attempt_count'] == 3 and before['retry_exhausted'] == 1
    assert before['effective_status'] == 'failed'
    assert before['approved'] == before['deployment_allowed'] == 0


@pytest.mark.parametrize('modes', [
    ('direct', 'direct'), ('direct', 'scheduled'), ('scheduled', 'scheduled'),
])
def test_concurrent_acquirers_cannot_spend_last_attempt_twice(tmp_path, modes):
    db, task_id, _ = queued_source(tmp_path)
    queue = TaskQueue(db)
    for _ in range(2):
        assert queue.acquire_next('previous-worker', require_target=True) is not None
        expire(db, task_id)
    queues = [TaskQueue(db), TaskQueue(db)]
    barrier = Barrier(2)

    def contend(index):
        barrier.wait(timeout=5)
        return acquire_using(queues[index], task_id, f'contender-{index}', modes[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(contend, index) for index in range(2)]
        tokens = [future.result(timeout=15) for future in futures]
    winners = [index for index, token in enumerate(tokens) if token is not None]
    assert len(winners) == 1
    winner = winners[0]
    state = TaskQueue(db).status(task_id)
    assert state['owner'] == f'contender-{winner}'
    assert state['attempt_count'] == 3 and state['retry_exhausted'] == 1
    assert sum(event['event'] == 'acquired' for event in queue.audit(task_id)) == 3
    expire(db, task_id)
    assert TaskQueue(db).acquire(task_id, 'late-direct') is None
    assert TaskQueue(db).acquire_next('late-scheduled', require_target=True) is None


def test_last_direct_lease_can_heartbeat_and_complete_without_reacquisition(tmp_path):
    db, task_id, _ = queued_source(tmp_path)
    queue = TaskQueue(db)
    for _ in range(2):
        assert queue.acquire_next('previous-worker', require_target=True) is not None
        expire(db, task_id)
    token = queue.acquire(task_id, 'last-worker')
    assert token is not None
    assert queue.status(task_id)['retry_exhausted'] == 1
    assert queue.status(task_id)['effective_status'] == 'leased'
    before = queue.status(task_id)
    assert queue.acquire(task_id, 'busy-contender') is None
    assert queue.status(task_id) == before
    assert queue.heartbeat(task_id, 'last-worker', token)
    assert queue.status(task_id)['attempt_count'] == 3
    queue.complete(task_id, 'last-worker', token)
    assert TaskQueue(db).status(task_id)['effective_status'] == 'done'
    assert TaskQueue(db).acquire(task_id, 'after-completion') is None


def test_direct_runner_can_complete_third_attempt_and_preserve_source(tmp_path):
    db, task_id, workspace = queued_source(tmp_path)
    bridge = PersistentTaskBridge(db)
    for _ in range(2):
        assert bridge.queue.acquire_next('previous-worker', require_target=True) is not None
        expire(db, task_id)
    original = (workspace / 'sample.py').read_bytes()
    result = DeveloperTaskRunner(bridge.queue, 'direct-runner').run_and_complete(
        bridge, task_id, workspace, 'sample.py')
    assert result['status'] == 'analyzed'
    state = PersistentTaskBridge(db).task_overview(task_id)
    assert state['queue_status'] == 'done' and state['attempt_count'] == 3
    assert state['approved'] is False and state['deployment_allowed'] is False
    assert (workspace / 'sample.py').read_bytes() == original


@pytest.mark.parametrize('method', ['run_check', 'run_analysis', 'run_and_complete'])
def test_exhausted_direct_runner_entrypoints_do_not_analyze(tmp_path, monkeypatch, method):
    db, task_id, workspace = queued_source(tmp_path)
    bridge = PersistentTaskBridge(db)
    for _ in range(3):
        assert bridge.queue.acquire_next('previous-worker', require_target=True) is not None
        expire(db, task_id)
    from central_ai.read_only_analyzer import ReadOnlyAnalyzer

    def forbidden(*args, **kwargs):
        raise AssertionError('EXHAUSTED_TASK_MUST_NOT_BE_ANALYZED')

    monkeypatch.setattr(ReadOnlyAnalyzer, 'analyze', forbidden)
    runner = DeveloperTaskRunner(TaskQueue(db), 'direct-runner')
    if method == 'run_check':
        result = runner.run_check(task_id)
    elif method == 'run_analysis':
        result = runner.run_analysis(task_id, workspace, 'sample.py')
    else:
        result = runner.run_and_complete(bridge, task_id, workspace, 'sample.py')
    assert result == {'status': 'not_acquired'}
    assert bridge.status(task_id)['status'] == 'planned'
    assert bridge.queue.status(task_id)['attempt_count'] == 3


def test_direct_attempt_budget_survives_an_actual_process_restart(tmp_path):
    db, task_id, _ = queued_source(tmp_path)
    assert TaskQueue(db).acquire(task_id, 'parent') is not None
    expire(db, task_id)
    script = '''import json, sys
from central_ai.task_queue import TaskQueue
queue = TaskQueue(sys.argv[1])
token = queue.acquire(sys.argv[2], 'child')
print(json.dumps({'acquired': token is not None, 'attempts': queue.status(sys.argv[2])['attempt_count']}))
'''
    child = subprocess.run([sys.executable, '-c', script, str(db), task_id],
                           check=True, capture_output=True, text=True, timeout=15)
    assert json.loads(child.stdout) == {'acquired': True, 'attempts': 2}
    expire(db, task_id)
    assert TaskQueue(db).acquire(task_id, 'restarted-parent') is not None
    expire(db, task_id)
    assert TaskQueue(db).acquire(task_id, 'fourth-process') is None


def test_reacquisition_invalidates_previous_owner_token(tmp_path):
    db, task_id, _ = queued_source(tmp_path)
    queue = TaskQueue(db)
    old = queue.acquire(task_id, 'old')
    expire(db, task_id)
    new = TaskQueue(db).acquire(task_id, 'new')
    assert old is not None and new is not None and old != new
    with pytest.raises(ValueError, match='HEARTBEAT_REJECTED'):
        queue.heartbeat(task_id, 'old', old)
    with pytest.raises(ValueError, match='OWNERSHIP_OR_LEASE_INVALID'):
        queue.complete(task_id, 'old', old)
    queue.complete(task_id, 'new', new)
    assert queue.status(task_id)['attempt_count'] == 2


@pytest.mark.parametrize('attempts,exhausted', [(3, 0), (0, 1)])
def test_direct_acquire_fails_closed_for_each_budget_guard(tmp_path, attempts, exhausted):
    db, task_id, _ = queued_source(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute('UPDATE task_queue SET attempt_count=?,retry_exhausted=? WHERE task_id=?',
                    (attempts, exhausted, task_id))
    queue = TaskQueue(db)
    before = queue.status(task_id)
    assert queue.acquire(task_id, 'must-refuse') is None
    assert queue.status(task_id) == before


def test_direct_acquire_migrates_legacy_queue_without_target_registry(tmp_path):
    db = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('''CREATE TABLE task_queue (
            task_id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('pending','leased','done')),
            owner TEXT, lease_token TEXT, lease_until TEXT,
            version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
            approved INTEGER NOT NULL DEFAULT 0 CHECK(approved=0),
            deployment_allowed INTEGER NOT NULL DEFAULT 0 CHECK(deployment_allowed=0))''')
    queue = TaskQueue(db)
    queue.enqueue('legacy-task')
    token = queue.acquire('legacy-task', 'legacy-worker')
    assert isinstance(token, str) and token
    assert TaskQueue(db).status('legacy-task')['attempt_count'] == 1
    assert TaskQueue(db).acquire('legacy-task', 'busy-contender') is None
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT name FROM sqlite_master WHERE name='task_file_targets'").fetchone() is None
    queue.complete('legacy-task', 'legacy-worker', token)
