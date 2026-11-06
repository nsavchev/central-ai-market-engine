"""Operator-only, one-attempt adapter connectivity check; never starts a worker.

The SQLite task/queue below are synthetic fixtures, not production analysis or
verification evidence. Only a fixed public prompt can leave this process.
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
    args = parser.parse_args()
    if not args.send_once:
        raise ValueError('EXPLICIT_SINGLE_REQUEST_REQUIRED')
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


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps(dict(acceptance='not_started_or_uncertain',error_type=type(error).__name__,retry_allowed=False)))
        sys.exit(1)
