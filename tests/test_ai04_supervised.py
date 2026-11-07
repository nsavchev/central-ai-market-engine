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
