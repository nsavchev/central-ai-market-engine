"""Operator-only, one-attempt adapter checks; never starts a scheduled worker.

Default is connectivity with synthetic queue state. --end-to-end uses the
existing task/analyzer/pipeline and actual isolated verifier in a private case.
--worker-check adds exactly three finite supervised cycles to --end-to-end.
Only fixed public prompts are sent; no production task database is opened.
"""
import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

SOURCE = 'c25f09ebae112ae025ccb4a78927a968a42428e7'
FILES = {
    'central_ai.task_storage': ('central_ai/task_storage.py', 'a9c432563a4b2ce1ec9ef900cec4708d34c84843d88a58a617feae34508dbc5f'),
    'central_ai.app': ('central_ai/app.py', 'a2ce6a9d4c5d2ea3adae79d24c66d81b3d41e0b6decee7650e9077eef281b9b1'),
}


E2E_SOURCE = '3e6595f965946482606af117ddca18b41a4bddba'
E2E_FILES = {'central_ai.app': ['central_ai/app.py', 'a2ce6a9d4c5d2ea3adae79d24c66d81b3d41e0b6decee7650e9077eef281b9b1'], 'central_ai.developer_task_runner': ['central_ai/developer_task_runner.py', 'db320eaa5277de984173b90593940065b6901f647723e624f0a0a47fec9fac62'], 'central_ai.developer_worker_coordinator': ['central_ai/developer_worker_coordinator.py', 'c180b4b03e803a863e48592b5fb59ebb89e27802b42c6f2f7f2708035fd88694'], 'central_ai.heartbeat_worker': ['central_ai/heartbeat_worker.py', '180102d35923a32c8f79c30faaa62c4ba01e356488d8b42b49de7fa970fe89b9'], 'central_ai.isolated_candidate': ['central_ai/isolated_candidate.py', '777e0a603a7ad26ea7ce587642be6cfb4fb227461de6c8137ee8195b07d45492'], 'central_ai.isolated_functional_verifier': ['central_ai/isolated_functional_verifier.py', '9abe73d86b46f2b998cf69ba37002868c377455d4fcb968d51e61ce94a70af25'], 'central_ai.persistent_bridge': ['central_ai/persistent_bridge.py', 'a1852f8c5b776d84e94281129c2c744a02b67ac57a2cea45708e90d5a54f03aa'], 'central_ai.persistent_workflow_v05': ['central_ai/persistent_workflow_v05.py', '2e967494a0343c74ea8b72b5eb1e993821d6bb00f628a100d80cddb64e8b656f'], 'central_ai.proposal_adapter': ['central_ai/proposal_adapter.py', '0925b669f31cee6d2c95c89a898c0602b034f226a5a7e6f43b6da34e52cd6a2f'], 'central_ai.read_only_analyzer': ['central_ai/read_only_analyzer.py', '5e0f4bfe7711f1a85f0e163c102642f7985c06f4fc1aeabd431375df100bc54b'], 'central_ai.review_handoff': ['central_ai/review_handoff.py', '7eee37a60d5e312db9ff5c001b1530a0e027e9ea85052b637ad095987f2d27e2'], 'central_ai.review_pipeline': ['central_ai/review_pipeline.py', 'ef1782a601b24875cd8ae3073012342226bd94a5a95e646962a20d7826e96f42'], 'central_ai.task_bridge': ['central_ai/task_bridge.py', '10543c92597c0fcbd4d5ec569d49d4ca02e8d6eb68250646e9bbcdffebb429ea'], 'central_ai.task_file_targets': ['central_ai/task_file_targets.py', '8e31b34677bab0b5dd09567d4b8252036aa6f7f92debf976d9979d9c1f4b4ffc'], 'central_ai.task_queue': ['central_ai/task_queue.py', 'd804b27c95923ab57534c979f2dba203ba7c1a23ac48dbf1ee055cbf223ec9d3'], 'central_ai.task_storage': ['central_ai/task_storage.py', 'a9c432563a4b2ce1ec9ef900cec4708d34c84843d88a58a617feae34508dbc5f'], 'central_ai.verified_review_pipeline': ['central_ai/verified_review_pipeline.py', '59d876d2979ae3b82ae416e430e89a7c4e308c295fd957fb56ee3615f26f3716'], 'central_ai.verifier_gate': ['central_ai/verifier_gate.py', '0a8f3680e455e574c47a3138ba61e74488f560ff42bc8edefcc6582a451b7abd'], 'central_ai.worker_batch': ['central_ai/worker_batch.py', 'bb8c2640f187a1fc0a5204186e05a9d6b279a0b9bfc6150c5506069c07931428'], 'central_ai.workflow_controller_v03': ['central_ai/workflow_controller_v03.py', '18ceb29345cf6a2b2adf4786aa98f1c8ea6350932b9c8e214160dcb678126e60'], 'developer_agent.v3.orchestrator': ['developer_agent/v3/orchestrator.py', '58b957ec403da132c23844b2ce90fba69b6e96129f71a6eeacaed58248639028'], 'developer_agent.v3.workflow': ['developer_agent/v3/workflow.py', '60c62b87cbe05a860fe4fc6c5278961dd6c7c178e625372ce70a93e4c4e48d11'], 'central_ai.__init__': ('central_ai/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'), 'runtime_lock': ('release/requirements-linux-amd64.lock', '78321ff8b94e1ced26eeb48b980f911b2f819c136b2c66ca1712c759e588289e')}

WORKER_SOURCE = '4b4f57f03e5c2c9a27e8cf97f56f9beea5041169'
WORKER_FILES = {'central_ai.app': ('central_ai/app.py', 'a2ce6a9d4c5d2ea3adae79d24c66d81b3d41e0b6decee7650e9077eef281b9b1'), 'central_ai.developer_task_runner': ('central_ai/developer_task_runner.py', 'db320eaa5277de984173b90593940065b6901f647723e624f0a0a47fec9fac62'), 'central_ai.developer_worker_coordinator': ('central_ai/developer_worker_coordinator.py', '613c22ed338fd861391af1e565badd1b1e6c07496a901796863888da9b4fbb27'), 'central_ai.heartbeat_worker': ('central_ai/heartbeat_worker.py', '180102d35923a32c8f79c30faaa62c4ba01e356488d8b42b49de7fa970fe89b9'), 'central_ai.isolated_candidate': ('central_ai/isolated_candidate.py', '777e0a603a7ad26ea7ce587642be6cfb4fb227461de6c8137ee8195b07d45492'), 'central_ai.isolated_functional_verifier': ('central_ai/isolated_functional_verifier.py', '9abe73d86b46f2b998cf69ba37002868c377455d4fcb968d51e61ce94a70af25'), 'central_ai.persistent_bridge': ('central_ai/persistent_bridge.py', 'a1852f8c5b776d84e94281129c2c744a02b67ac57a2cea45708e90d5a54f03aa'), 'central_ai.persistent_workflow_v05': ('central_ai/persistent_workflow_v05.py', '2e967494a0343c74ea8b72b5eb1e993821d6bb00f628a100d80cddb64e8b656f'), 'central_ai.proposal_adapter': ('central_ai/proposal_adapter.py', '0925b669f31cee6d2c95c89a898c0602b034f226a5a7e6f43b6da34e52cd6a2f'), 'central_ai.read_only_analyzer': ('central_ai/read_only_analyzer.py', '5e0f4bfe7711f1a85f0e163c102642f7985c06f4fc1aeabd431375df100bc54b'), 'central_ai.review_handoff': ('central_ai/review_handoff.py', '7eee37a60d5e312db9ff5c001b1530a0e027e9ea85052b637ad095987f2d27e2'), 'central_ai.review_pipeline': ('central_ai/review_pipeline.py', 'ef1782a601b24875cd8ae3073012342226bd94a5a95e646962a20d7826e96f42'), 'central_ai.task_bridge': ('central_ai/task_bridge.py', '10543c92597c0fcbd4d5ec569d49d4ca02e8d6eb68250646e9bbcdffebb429ea'), 'central_ai.task_file_targets': ('central_ai/task_file_targets.py', '8e31b34677bab0b5dd09567d4b8252036aa6f7f92debf976d9979d9c1f4b4ffc'), 'central_ai.task_queue': ('central_ai/task_queue.py', 'd804b27c95923ab57534c979f2dba203ba7c1a23ac48dbf1ee055cbf223ec9d3'), 'central_ai.task_storage': ('central_ai/task_storage.py', 'cacbf20954230baed7784732cdf53534ef3a8d600f820730ff49c9933798f73e'), 'central_ai.verified_review_pipeline': ('central_ai/verified_review_pipeline.py', '312322213eba2c4e456da62ff19d45fbb4a65c52bba6d9d9eeda156d4116f3f3'), 'central_ai.verifier_gate': ('central_ai/verifier_gate.py', '0a8f3680e455e574c47a3138ba61e74488f560ff42bc8edefcc6582a451b7abd'), 'central_ai.worker_batch': ('central_ai/worker_batch.py', 'f47de4c8fce08756202254c924df4e8b1834fc7d39cf56d0c546c1f29cc5e8bf'), 'central_ai.worker_scheduler': ('central_ai/worker_scheduler.py', '7d5de5293ec7e9f42698aec094a58f7a726fd4e011ae7506384811e6955d1034'), 'central_ai.worker_supervised': ('central_ai/worker_supervised.py', '59851ba6ea6c4d130fbbc17af780532f404611e2b546ad7defec948d03a70309'), 'central_ai.workflow_controller_v03': ('central_ai/workflow_controller_v03.py', '18ceb29345cf6a2b2adf4786aa98f1c8ea6350932b9c8e214160dcb678126e60'), 'developer_agent.v3.orchestrator': ('developer_agent/v3/orchestrator.py', '58b957ec403da132c23844b2ce90fba69b6e96129f71a6eeacaed58248639028'), 'developer_agent.v3.workflow': ('developer_agent/v3/workflow.py', '60c62b87cbe05a860fe4fc6c5278961dd6c7c178e625372ce70a93e4c4e48d11'), 'central_ai.__init__': ('central_ai/__init__.py', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'), 'runtime_lock': ('release/requirements-linux-amd64.lock', '78321ff8b94e1ced26eeb48b980f911b2f819c136b2c66ca1712c759e588289e')}

def probe(directory, transport=None):
    import hashlib, json, secrets, sqlite3
    from datetime import datetime, timezone, timedelta
    import httpx
    from central_ai.app import make_openai_generator
    from central_ai.task_storage import TaskStorage
    stats = {'attempts': 0}
    base = transport if transport is not None else httpx.AsyncHTTPTransport(retries=0, trust_env=False)

    class ObservedStream(httpx.AsyncByteStream):
        def __init__(self, stream):
            self.stream = stream
            self.body = bytearray()
        async def __aiter__(self):
            async for chunk in self.stream:
                if len(self.body) + len(chunk) <= 128*1024:
                    self.body.extend(chunk)
                yield chunk
        async def aclose(self):
            try:
                data = json.loads(self.body)
                usage = data.get('usage', {})
                if all(type(usage.get(k)) is int and 0 <= usage[k] <= 1000000
                       for k in ('prompt_tokens','completion_tokens','total_tokens')):
                    stats['usage'] = {k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens')}
            except (ValueError, TypeError, AttributeError):
                pass
            await self.stream.aclose()

    class OneRequest(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if stats['attempts'] or str(request.url) != 'https://api.openai.com/v1/chat/completions':
                raise ValueError('ACCEPTANCE_REQUEST_BLOCKED')
            expected = dict(model='gpt-4.1-mini', max_tokens=16,
                            messages=[dict(role='user', content='Return exactly OK.')])
            if request.method != 'POST' or json.loads(request.content) != expected:
                raise ValueError('ACCEPTANCE_PAYLOAD_BLOCKED')
            stats['attempts'] += 1
            response = await base.handle_async_request(request)
            stats['http_status'] = response.status_code
            response.stream = ObservedStream(response.stream)
            return response
        async def aclose(self):
            await base.aclose()

    report = dict(scope='adapter_connectivity_only', model='gpt-4.1-mini', max_output_tokens=16,
                  production_tasks_modified=False, worker_activated=False, generated_code_executed=False)
    try:
        storage = TaskStorage(str(directory)+'/fixture.sqlite')
        task_id, nonce = secrets.token_hex(16), secrets.token_hex(16)
        stamp = datetime.now(timezone.utc)
        digest = hashlib.sha256(b'public synthetic fixture; no production source').hexdigest()
        task = dict(task_id=task_id, status='analyzed', approved=False, deployment_allowed=False,
                    task=dict(task='Return exactly OK.', approved=False, deployment_allowed=False),
                    analysis=dict(source_sha256=digest))
        with sqlite3.connect(storage.db_path) as conn:
            conn.execute('CREATE TABLE task_queue (task_id TEXT PRIMARY KEY,status TEXT,approved INTEGER,deployment_allowed INTEGER)')
            conn.execute('INSERT INTO tasks VALUES (?,?,?,?,?)',
                         (task_id,'analyzed',json.dumps(task),stamp.isoformat(),stamp.isoformat()))
            conn.execute('INSERT INTO task_queue VALUES (?,?,?,?)',(task_id,'done',0,0))
        generate = make_openai_generator(enabled='YES', database=str(storage.db_path), transport=OneRequest())
        storage.begin_verification(task_id, nonce)
        # Placeholder image/test bindings belong to this transport-only fixture;
        # no Docker verifier, candidate or independent test execution is asserted.
        request = storage.begin_generation(task_id,nonce,generate.generator_id,digest,'fixture@sha256:'+digest)
        receipt = dict(schema='generation-admission-v1',generation_authorized=True,
            binding=dict(request['binding']),scope='generate_only',disclosure='task_description_only',
            authorization_id='operator-single-check-'+nonce,budget_period=stamp.strftime('%Y-%m'),
            budget_limit_microuros=1000,budget_call_limit=1,reserved_microuros=1000,
            model='gpt-4.1-mini',max_output_tokens=16,expires_at=(stamp+timedelta(minutes=1)).isoformat(),
            approved=False,deployment_allowed=False)
        request['admission'] = storage.authorize_generation(task_id,nonce,receipt)
        answer = generate(request)
        storage.complete_generation(task_id,nonce,answer,request['admission']['admission_sha256'])
        if answer.strip() != 'OK':
            raise ValueError('UNEXPECTED_ACCEPTANCE_ANSWER')
        report.update(acceptance='passed', journal_completed=True)
    except BaseException as error:
        report.update(acceptance='failed', error_type=type(error).__name__)
    report.update(stats)
    return report


def claim_once(case):
    case = Path(case)
    if not case.is_absolute() or case.resolve() != case:
        raise ValueError('INVALID_ACCEPTANCE_DIRECTORY')
    case.mkdir(mode=0o700, parents=False, exist_ok=True)
    stat = case.stat()
    if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise ValueError('ACCEPTANCE_DIRECTORY_NOT_PRIVATE')
    fd = os.open(case/'attempt.started', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd,'w') as out:
        out.write('One attempt reserved. Do not delete or automatically retry.\n')
        out.flush()
        os.fsync(out.fileno())
    fd = os.open(case, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--case-directory', required=True)
    parser.add_argument('--send-once', action='store_true')
    parser.add_argument('--end-to-end', action='store_true')
    parser.add_argument('--worker-check', action='store_true')
    args = parser.parse_args()
    if not args.send_once:
        raise ValueError('EXPLICIT_SINGLE_REQUEST_REQUIRED')
    if args.worker_check and not args.end_to_end:
        raise ValueError('E2E_WORKER_MODE_REQUIRES_END_TO_END')
    if args.end_to_end:
        return end_to_end_main(args)
    modules = {}
    for name, (path, expected) in FILES.items():
        with urlopen('https://raw.githubusercontent.com/nsavchev/central-ai-market-engine/'+SOURCE+'/'+path, timeout=30) as response:
            source = response.read(256*1024+1)
        if len(source)>256*1024 or hashlib.sha256(source).hexdigest()!=expected:
            raise ValueError('PINNED_SOURCE_MISMATCH')
        modules[name] = source.decode()
    case = claim_once(args.case_directory)
    program = 'import sys,types,json,tempfile\n'
    program += 'modules='+repr(modules)+'\n'
    program += "package=types.ModuleType('central_ai'); package.__path__=[]; sys.modules['central_ai']=package\n"
    program += "for name,source in modules.items():\n module=types.ModuleType(name); sys.modules[name]=module; exec(compile(source,name,'exec'),module.__dict__)\n"
    program += inspect.getsource(probe)+'\n'
    program += "with tempfile.TemporaryDirectory(prefix='central-ai-adapter-check-') as directory:\n report=probe(directory)\nprint(json.dumps(report,sort_keys=True))\n"
    try:
        result = subprocess.run(['docker','exec','-i',args.container,'python','-'],input=program,
                                text=True,capture_output=True,timeout=90)
        if result.returncode or len(result.stdout)>8192:
            raise RuntimeError('ACCEPTANCE_PROCESS_FAILED')
        report = json.loads(result.stdout)
        if not isinstance(report,dict) or report.get('scope')!='adapter_connectivity_only':
            raise ValueError('INVALID_ACCEPTANCE_REPORT')
    except BaseException as error:
        report = dict(acceptance='unconfirmed',error_type=type(error).__name__,retry_allowed=False)
    (case/'report.json').write_text(json.dumps(report,sort_keys=True)+'\n')
    print(json.dumps(report,sort_keys=True))
    return 0 if report.get('acceptance')=='passed' else 1



def run_e2e_case(root, image, key_container=None, *, generator_factory=None, verifier=None, worker_cycles=0):
    """One synthetic task through actual owners; no production paths or retries."""
    import hashlib, hmac, json, os, secrets, subprocess, time
    from pathlib import Path
    from datetime import datetime, timezone, timedelta
    from central_ai.persistent_bridge import PersistentTaskBridge
    from central_ai.task_file_targets import TaskFileTargets
    from central_ai.task_storage import TaskStorage
    from central_ai.worker_batch import run_batch
    from central_ai.verifier_gate import make_hmac_review_authorizer
    from central_ai.verified_review_pipeline import prepare_and_verify
    from central_ai.app import make_openai_generator
    root = Path(root)
    report = dict(scope='isolated_worker_generation_and_verification' if worker_cycles else 'isolated_generation_and_verification', provider_mode='real' if generator_factory is None else 'mock',
                  verifier_mode='docker' if verifier is None else 'mock', worker_activated=False,
                  production_tasks_modified=False, approved=False, deployment_allowed=False,
                  model='gpt-4.1-mini', max_output_tokens=128)
    original_key = os.environ.get('OPENAI_API_KEY')
    try:
        if type(worker_cycles) is not int or worker_cycles not in (0,3):
            raise ValueError('E2E_WORKER_CYCLE_LIMIT_INVALID')
        database = root/'e2e.sqlite'
        if database.exists():
            raise ValueError('E2E_CASE_ALREADY_STARTED')
        source = root/'source'; source.mkdir(mode=0o700)
        original = source/'sample.py'
        original_bytes = b'def f(a, b):\n    return a + b\n'
        original.write_bytes(original_bytes)
        test = root/'trusted_test.py'
        test_bytes = b"import sys\nsys.path.insert(0, '/sandbox')\nfrom candidate import f\nassert f(3, 4) == 12\nassert f(-2, 5) == -10\nassert f(0, 99) == 0\nassert f(-3, -4) == 12\n"
        test.write_bytes(test_bytes)
        test.chmod(0o600)
        test_digest = hashlib.sha256(test_bytes).hexdigest()
        bridge = PersistentTaskBridge(database)
        prompt = 'Implement def f(a, b) to return a * b. Return only one python fenced code block; no comments, imports or prose.'
        task_id = bridge.submit(prompt)['task_id']
        targets = TaskFileTargets(database); targets.initialize()
        targets.register(task_id, str(source), 'sample.py')
        if not worker_cycles:
            analysis = run_batch(enabled='YES',database=str(database),agent='isolated-e2e-check',
                                 max_tasks=1,idle_checks=1,sleep=lambda _:None)
            if analysis['processed'] != 1:
                raise ValueError('E2E_ANALYSIS_NOT_COMPLETED')
            report['analysis_completed'] = True
        storage = TaskStorage(database)
        paths = []
        for name in ('handoffs','proposals','candidates'):
            path=root/name; path.mkdir(mode=0o700); paths.append(str(path))
        key = secrets.token_bytes(32)  # Ephemeral test authority, never sent to the model.
        def issue(binding):
            if binding['test_sha256']!=test_digest or binding['image']!=image:
                raise ValueError('E2E_REVIEW_BINDING_CHANGED')
            now=int(time.time())
            receipt=dict(schema='review-hmac-sha256-v1',binding=dict(binding),
                reviewer_id='operator-e2e-only',authorization_id='e2e-'+binding['nonce'],issued_at=now,
                expires_at=now+60,verification_authorized=True,approved=False,deployment_allowed=False)
            payload=json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            return dict(receipt,mac=hmac.new(key,payload,'sha256').hexdigest())
        authorize=make_hmac_review_authorizer(reviewer_keys={'operator-e2e-only':key},request_receipt=issue)
        def admission(binding):
            now=datetime.now(timezone.utc)
            return dict(schema='generation-admission-v1',generation_authorized=True,binding=dict(binding),
                scope='generate_only',disclosure='task_description_only',authorization_id='e2e-'+binding['nonce'],
                budget_period=now.strftime('%Y-%m'),budget_limit_microuros=1000,budget_call_limit=1,
                reserved_microuros=1000,model='gpt-4.1-mini',max_output_tokens=128,
                expires_at=(now+timedelta(minutes=1)).isoformat(),approved=False,deployment_allowed=False)
        if generator_factory is None:
            result=subprocess.run(['docker','exec',key_container,'python','-c',
                'import os,json; print(json.dumps(os.environ.get("OPENAI_API_KEY", "")))'],
                text=True,capture_output=True,timeout=15)
            if result.returncode or len(result.stdout)>8192:
                raise ValueError('E2E_KEY_NOT_AVAILABLE')
            api_key=json.loads(result.stdout)
            if not isinstance(api_key,str) or not 20 <= len(api_key)<=4096:
                raise ValueError('E2E_KEY_NOT_AVAILABLE')
            os.environ['OPENAI_API_KEY']=api_key
            del api_key, result
            generate=make_openai_generator(enabled='YES',database=str(database))
        else:
            generate=generator_factory(str(database))
        options={} if verifier is None else dict(verifier=verifier)
        generator_id=generate.generator_id
        report['generator_invocations']=0
        def once(request):
            if report['generator_invocations']:
                raise ValueError('E2E_GENERATOR_REPLAY_BLOCKED')
            report['generator_invocations']+=1
            return generate(request)
        job=dict(handoffs=paths[0],proposals=paths[1],candidates=paths[2],trusted_test_file=str(test),
                 trusted_test_sha256=test_digest,image=image)
        if worker_cycles:
            from central_ai.verified_review_pipeline import make_worker_review_handler
            from central_ai.worker_scheduler import scheduled_cycles
            from central_ai.worker_supervised import run_supervised
            handler=make_worker_review_handler(enabled='YES',database=str(database),jobs={task_id:job},
                generator=once,generator_id=generator_id,generation_authorization_check=admission,
                authorization_check=authorize,**options)
            def bounded_batch(**kwargs):
                return run_batch(**kwargs,idle_checks=1,sleep=lambda _:None)
            def schedule(**kwargs):
                return scheduled_cycles(**kwargs,batch=bounded_batch)
            result=run_supervised(enabled='YES',database=str(database),agent='isolated-worker-check',
                lock_path=str(root/'worker.lock'),status_path=str(root/'worker-status.json'),
                cycles=worker_cycles,interval=1,max_tasks=1,scheduler=schedule,review_handler=handler)
            if result.get('cycles')!=3 or result.get('processed')!=1 or report['generator_invocations']!=1:
                raise ValueError('E2E_WORKER_RESULT_INVALID')
            report.update(bounded_worker_run=True,persistent_worker_enabled_by_check=False,
                          worker_cycles_completed=3,worker_processed=1,post_completion_idle_cycles=2)
            saved=storage.get(task_id)
            outcome=dict(saved['verification']['outcome'],audit_recorded=True)
            report['analysis_completed']=saved['status']=='analyzed'
        else:
            outcome=prepare_and_verify(enabled='YES',database=str(database),task_id=task_id,
                **job,authorization_check=authorize,generation_authorization_check=admission,
                generator=once,generator_id=generator_id,**options)
            saved=storage.get(task_id)
        source_unchanged=original.read_bytes()==original_bytes
        test_unchanged=test.read_bytes()==test_bytes
        resources=saved['verification']['resources']
        if (not source_unchanged or not test_unchanged or not outcome['audit_recorded']
                or saved['generation']['phase']!='completed' or saved['verification']['phase']!='completed'
                or saved['approved'] is not False or saved['deployment_allowed'] is not False
                or saved['generation']['dispatch']['max_output_tokens']!=128
                or outcome['quarantine_required'] or Path(resources['snapshot_directory']).exists()):
            raise ValueError('E2E_ACCEPTANCE_CONFLICT')
        report.update(acceptance='passed' if outcome['tests_passed'] else 'candidate_failed',
            test_status=outcome['test_status'],generation_completed=True,verification_journal_completed=True,
            source_unchanged=source_unchanged,trusted_tests_unchanged=test_unchanged,
            snapshot_removed=not Path(resources['snapshot_directory']).exists())
    except BaseException as error:
        report.update(acceptance='failed_or_uncertain',error_type=type(error).__name__)
    finally:
        if original_key is None:
            os.environ.pop('OPENAI_API_KEY',None)
        else:
            os.environ['OPENAI_API_KEY']=original_key
    return report


def end_to_end_main(args):
    import re
    from concurrent.futures import ThreadPoolExecutor
    worker_check=getattr(args,'worker_check',False)
    bundle_source=WORKER_SOURCE if worker_check else E2E_SOURCE
    bundle_files=WORKER_FILES if worker_check else E2E_FILES
    case=claim_once(args.case_directory)
    package=case/'package'; package.mkdir(mode=0o700)
    def download(item):
        name,(path,expected)=item
        with urlopen('https://raw.githubusercontent.com/nsavchev/central-ai-market-engine/'+bundle_source+'/'+path,timeout=30) as response:
            data=response.read(256*1024+1)
        if len(data)>256*1024 or hashlib.sha256(data).hexdigest()!=expected:
            raise ValueError('E2E_SOURCE_MISMATCH')
        return path,data
    with ThreadPoolExecutor(max_workers=4) as pool:
        for path,data in pool.map(download,bundle_files.items()):
            target=package/path; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
    # A private virtualenv leaves system and production dependencies unchanged.
    venv=case/'venv'
    for command in ([sys.executable,'-m','venv',str(venv)],
                    [str(venv/'bin/python'),'-m','pip','install','--require-hashes','--only-binary=:all:',
                     '-r',str(package/'release/requirements-linux-amd64.lock')]):
        result=subprocess.run(command,text=True,capture_output=True,timeout=120)
        if result.returncode:
            raise RuntimeError('E2E_DEPENDENCY_SETUP_FAILED')
    result=subprocess.run(['docker','pull','python:3.12-alpine'],text=True,capture_output=True,timeout=120)
    if result.returncode:
        raise RuntimeError('E2E_TEST_IMAGE_UNAVAILABLE')
    result=subprocess.run(['docker','image','inspect','python:3.12-alpine','--format','{{index .RepoDigests 0}}'],
                          text=True,capture_output=True,timeout=15)
    image=result.stdout.strip()
    if result.returncode or not re.fullmatch(r'python@sha256:[0-9a-f]{64}',image):
        raise ValueError('E2E_IMAGE_NOT_PINNED')
    program='import sys,json\nsys.path.insert(0,'+repr(str(package))+')\n'+inspect.getsource(run_e2e_case)
    program+='\nreport=run_e2e_case('+repr(str(case))+','+repr(image)+','+repr(args.container)+',worker_cycles='+str(3 if worker_check else 0)+')\nprint(json.dumps(report,sort_keys=True))\n'
    result=subprocess.run([str(venv/'bin/python'),'-c',program],text=True,capture_output=True,timeout=150)
    if result.returncode or len(result.stdout)>8192:
        raise RuntimeError('E2E_PROCESS_OUTCOME_UNCERTAIN')
    report=json.loads(result.stdout)
    expected_scope='isolated_worker_generation_and_verification' if worker_check else 'isolated_generation_and_verification'
    if report.get('scope')!=expected_scope or report.get('provider_mode')!='real' or report.get('verifier_mode')!='docker':
        raise ValueError('E2E_REPORT_INVALID')
    (case/'report.json').write_text(json.dumps(report,sort_keys=True)+'\n')
    print(json.dumps(report,sort_keys=True))
    return 0 if report.get('acceptance')=='passed' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        report=dict(acceptance='not_started_or_uncertain',error_type=type(error).__name__,retry_allowed=False)
        code=str(error)
        if code.startswith('E2E_') and all(char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for char in code):
            report['error_code']=code
        print(json.dumps(report))
        sys.exit(1)
