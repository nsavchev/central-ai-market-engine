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


@pytest.mark.parametrize('flag',['','NO'])
def test_cli_default_review_disabled_preserves_analysis_only(monkeypatch,flag):
    import central_ai.worker_supervised as service
    monkeypatch.setenv('CENTRAL_WORKER_REVIEW_ENABLED',flag)
    monkeypatch.delenv('CENTRAL_WORKER_REVIEW_CONFIG',raising=False)
    seen=[]
    monkeypatch.setattr(service,'run_supervised',lambda **kw:seen.append(kw) or {'status':'complete'})
    service.main()
    assert 'review_handler' not in seen[0]


@pytest.mark.parametrize('service_enabled,flag,location',[('','YES','/private/policy.json'),
    ('YES','NO','/private/policy.json'),('YES','YES',''),('YES','invalid','')])
def test_cli_misconfigured_review_never_loads_key_or_runs(monkeypatch,service_enabled,flag,location):
    import central_ai.worker_supervised as service
    import central_ai.verified_review_pipeline as pipeline
    monkeypatch.setenv('CENTRAL_SUPERVISED_SERVICE_ENABLED',service_enabled)
    monkeypatch.setenv('CENTRAL_WORKER_REVIEW_ENABLED',flag)
    monkeypatch.setenv('CENTRAL_WORKER_REVIEW_CONFIG',location)
    monkeypatch.setattr(pipeline,'load_worker_review_config',lambda **kw:pytest.fail('must not read policy/key'))
    monkeypatch.setattr(service,'run_supervised',lambda **kw:pytest.fail('must not run'))
    with pytest.raises(ValueError):service.main()


def test_cli_explicit_review_passes_config_to_supervised_startup(monkeypatch):
    import central_ai.worker_supervised as service
    monkeypatch.setenv('CENTRAL_SUPERVISED_SERVICE_ENABLED','YES')
    monkeypatch.setenv('CENTRAL_WORKER_REVIEW_ENABLED','YES')
    monkeypatch.setenv('CENTRAL_WORKER_REVIEW_CONFIG','/private/policy.json')
    monkeypatch.setenv('CENTRAL_TASK_DB','/private/state/tasks.sqlite')
    seen=[]
    monkeypatch.setattr(service,'run_supervised',lambda **kw:seen.append(kw) or {'status':'complete'})
    service.main()
    assert seen[0]['review_config_path']=='/private/policy.json'
    assert 'review_handler' not in seen[0]

@pytest.mark.parametrize('state',['blocked','candidate_failed','cleanup_uncertain'])
def test_cli_review_failure_exit_status(monkeypatch,state):
    import central_ai.worker_supervised as service
    monkeypatch.delenv('CENTRAL_WORKER_REVIEW_ENABLED',raising=False)
    monkeypatch.delenv('CENTRAL_WORKER_REVIEW_CONFIG',raising=False)
    monkeypatch.setattr(service,'run_supervised',lambda **kw:dict(status='complete',review_state=state))
    with pytest.raises(SystemExit) as error:service.main()
    assert error.value.code==1


def test_review_load_error_replaces_stale_success_before_scheduler(monkeypatch,tmp_path):
    import central_ai.developer_worker_coordinator as owner
    db=tmp_path/'tasks.sqlite';db.touch();status=tmp_path/'status.json'
    status.write_text('{"state":"verified"}')
    def load(**kwargs):
        assert json.loads(status.read_text())['state']=='starting'
        raise ValueError('private-credential-detail')
    monkeypatch.setattr(owner.DeveloperWorkerCoordinator,'configured_review_handler',load)
    with pytest.raises(ValueError):run_supervised(enabled='YES',database=str(db),agent='test',
        lock_path=str(tmp_path/'worker.lock'),status_path=str(status),review_config_path='/private/policy.json',
        scheduler=lambda **kw:pytest.fail('must not schedule'))
    record=json.loads(status.read_text())
    assert record['state']=='blocked' and record['error_type']=='ValueError'
    assert 'private-credential-detail' not in status.read_text()


def test_invalid_loaded_review_handler_cannot_downgrade_to_analysis(monkeypatch,tmp_path):
    import central_ai.developer_worker_coordinator as owner
    db=tmp_path/'tasks.sqlite';db.touch();status=tmp_path/'status.json'
    monkeypatch.setattr(owner.DeveloperWorkerCoordinator,'configured_review_handler',lambda **kw:None)
    with pytest.raises(ValueError,match='REVIEW_STATUS_REQUIRED'):
        run_supervised(enabled='YES',database=str(db),agent='test',lock_path=str(tmp_path/'worker.lock'),
            status_path=str(status),review_config_path='/private/policy.json',
            scheduler=lambda **kw:pytest.fail('must not downgrade to analysis'))
    assert json.loads(status.read_text())['state']=='blocked'


@pytest.mark.parametrize('fails', [False, True])
def test_cli_restores_existing_sigterm_handler_after_success_or_failure(monkeypatch, fails):
    import signal
    import central_ai.worker_supervised as service
    monkeypatch.delenv('CENTRAL_WORKER_REVIEW_ENABLED', raising=False)
    monkeypatch.delenv('CENTRAL_WORKER_REVIEW_CONFIG', raising=False)
    previous = signal.getsignal(signal.SIGTERM)
    def caller_handler(signum, frame):
        pytest.fail('caller handler must not run during the scoped CLI call')
    def run(**kwargs):
        assert callable(signal.getsignal(signal.SIGTERM))
        assert signal.getsignal(signal.SIGTERM) is not caller_handler
        if fails:
            raise RuntimeError('synthetic scheduler failure')
        return dict(status='complete')
    monkeypatch.setattr(service, 'run_supervised', run)
    signal.signal(signal.SIGTERM, caller_handler)
    try:
        if fails:
            with pytest.raises(RuntimeError, match='synthetic scheduler failure'):
                service.main()
        else:
            service.main()
        assert signal.getsignal(signal.SIGTERM) is caller_handler
    finally:
        signal.signal(signal.SIGTERM, previous)


@pytest.mark.skipif(not hasattr(__import__('os'), 'fork'), reason='requires POSIX fork and SIGTERM')
def test_cli_real_sigterm_during_scheduled_wait_preserves_unwind_and_releases_lock(tmp_path):
    import fcntl
    import multiprocessing
    import os
    import signal
    import time
    import central_ai.worker_supervised as service
    from central_ai.worker_scheduler import scheduled_cycles

    database = tmp_path/'tasks.sqlite'
    database.touch()
    lock = tmp_path/'supervisor.lock'
    status = tmp_path/'supervisor-status.json'
    context = multiprocessing.get_context('fork')
    receive, send = context.Pipe(duplex=True)

    def child():
        receive.close()
        original = service.run_supervised
        previous = signal.getsignal(signal.SIGTERM)
        batches = []
        def batch(**kwargs):
            batches.append(kwargs)
            return dict(processed=0)
        def waiting(seconds):
            send.send('waiting')
            try:
                time.sleep(seconds)
            finally:
                send.send('cleanup_started')
                # Pipe acknowledgement keeps the second signal inside unwind
                # without a timing race or shared Event condition lock.
                assert send.poll(10) and send.recv() == 'release_cleanup'
                send.send('cleanup_finished')
        def schedule(**kwargs):
            return scheduled_cycles(**kwargs, batch=batch, sleep=waiting)
        service.run_supervised = lambda **kwargs: original(**kwargs, scheduler=schedule)
        os.environ.update(CENTRAL_SUPERVISED_SERVICE_ENABLED='YES',
            CENTRAL_TASK_DB=str(database), CENTRAL_WORKER_AGENT='ci-sigterm',
            CENTRAL_SCHEDULER_LOCK=str(lock), CENTRAL_SUPERVISOR_STATUS=str(status),
            CENTRAL_SCHEDULER_CYCLES='2', CENTRAL_SCHEDULER_INTERVAL='60',
            CENTRAL_WORKER_MAX_TASKS='1')
        os.environ.pop('CENTRAL_WORKER_REVIEW_ENABLED', None)
        os.environ.pop('CENTRAL_WORKER_REVIEW_CONFIG', None)
        try:
            service.main()
        except service.SupervisorStopRequested:
            send.send(dict(stopped=True, batches=len(batches),
                handler_restored=signal.getsignal(signal.SIGTERM) == previous))
            raise SystemExit(1)
        finally:
            send.close()

    process = context.Process(target=child)
    process.start()
    send.close()
    try:
        assert receive.poll(10) and receive.recv() == 'waiting'
        started = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        assert receive.poll(5) and receive.recv() == 'cleanup_started'
        os.kill(process.pid, signal.SIGTERM)
        receive.send('release_cleanup')
        assert receive.poll(5) and receive.recv() == 'cleanup_finished'
        assert receive.poll(5)
        assert receive.recv() == dict(stopped=True, batches=1, handler_restored=True)
        process.join(5)
        elapsed = time.monotonic() - started
        assert process.exitcode == 1 and elapsed < 10
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        receive.close()

    record = json.loads(status.read_text())
    assert record['state'] == 'failed'
    assert record['error_type'] == 'SupervisorStopRequested'
    assert 'SUPERVISOR_STOP_REQUESTED' not in status.read_text()
    assert database.read_bytes() == b''
    with lock.open() as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print('SUPERVISOR_CLI_SIGTERM_UNWIND_PASSED', round(elapsed, 3))
