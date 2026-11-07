"""Central AI Task Storage v0.2."""

import json
import hashlib
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

OPENAI_GENERATOR_ID = 'openai-bounded-v1'


class TaskStorage:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(
            parents=True, exist_ok=True
        )
        self._initialize()

    def _connect(self):
        return sqlite3.connect(
            str(self.db_path), timeout=10
        )

    def _initialize(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def save(self, task, conn=None):
        if not isinstance(task, dict):
            raise ValueError("INVALID_TASK")

        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("INVALID_TASK_ID")

        if task.get("approved") is not False:
            raise ValueError("APPROVAL_BLOCKED")

        if task.get("deployment_allowed") is not False:
            raise ValueError("DEPLOYMENT_BLOCKED")

        nested = task.get("task")
        if not isinstance(nested, dict):
            raise ValueError("INVALID_TASK_PAYLOAD")

        if nested.get("approved") is not False:
            raise ValueError("APPROVAL_BLOCKED")

        if nested.get("deployment_allowed") is not False:
            raise ValueError("DEPLOYMENT_BLOCKED")

        if task.get("status") != "planned":
            raise ValueError("INVALID_INITIAL_STATUS")

        if nested.get("stage") != "plan":
            raise ValueError("INVALID_INITIAL_STAGE")

        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(task)

        if conn is None:
            with self._connect() as own_conn:
                return self.save(task, conn=own_conn)
        if not isinstance(conn, sqlite3.Connection):
            raise ValueError('INVALID_CONNECTION')
        conn.execute("""
            INSERT INTO tasks
            (task_id, status, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            task_id, "planned", payload, now, now
        ))

        return task_id

    def get(self, task_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM tasks WHERE task_id=?",
                (task_id,)
            ).fetchone()

        return json.loads(row[0]) if row else None

    def list_tasks(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM tasks ORDER BY created_at"
            ).fetchall()

        return [json.loads(row[0]) for row in rows]

    def _review_task(self, conn, task_id):
        row = conn.execute('SELECT status,payload FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        if row is None:
            raise ValueError('TASK_NOT_FOUND')
        task = json.loads(row[1])
        nested = task.get('task')
        if (row[0] != 'analyzed' or task.get('status') != 'analyzed'
                or task.get('approved') is not False or task.get('deployment_allowed') is not False
                or not isinstance(nested, dict) or nested.get('approved') is not False
                or nested.get('deployment_allowed') is not False):
            raise ValueError('VERIFICATION_TASK_NOT_READY')
        queue = conn.execute('SELECT status,approved,deployment_allowed FROM task_queue WHERE task_id=?',
                             (task_id,)).fetchone()
        if queue != ('done', 0, 0):
            raise ValueError('VERIFICATION_TASK_NOT_READY')
        return task

    def _write_review_task(self, conn, task_id, task):
        cursor = conn.execute("UPDATE tasks SET payload=?,updated_at=? WHERE task_id=? AND status='analyzed'",
                              (json.dumps(task, allow_nan=False), datetime.now(timezone.utc).isoformat(), task_id))
        if cursor.rowcount != 1:
            raise RuntimeError('VERIFICATION_AUDIT_WRITE_FAILED')

    @staticmethod
    def check_verification_barrier(tasks):
        """Shared read/dispatch guard; unresolved intents require reconciliation."""
        for task in tasks:
            if 'verification' not in task:
                continue
            audit = task['verification']
            if (not isinstance(audit, dict) or audit.get('schema') != 'task-verification-v1'
                    or audit.get('phase') not in ('preparing','running','completed','blocked','quarantined')
                    or audit.get('approved') is not False or audit.get('deployment_allowed') is not False):
                raise ValueError('INVALID_VERIFICATION_AUDIT')
            if audit['phase'] in ('preparing','running','quarantined'):
                raise ValueError('VERIFICATION_DATABASE_BLOCKED')

    def begin_verification(self, task_id, nonce):
        """Reserve a one-shot verification intent in the existing task payload.

        Incomplete or quarantined intents serialize verification within this DB.
        They require operator reconciliation; this method never clears them.
        """
        if not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce):
            raise ValueError('INVALID_VERIFICATION_NONCE')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            revision = task.get('revision')
            if revision is not None and (not isinstance(revision, dict)
                    or revision.get('schema') != 'revision-v1'
                    or task.get('analysis', {}).get('source_sha256') != revision.get('source_sha256')):
                raise ValueError('REVISION_SOURCE_CHANGED')
            if 'verification' in task:
                raise ValueError('VERIFICATION_ALREADY_STARTED')
            self.check_verification_barrier(json.loads(row[0]) for row in conn.execute('SELECT payload FROM tasks'))
            now = datetime.now(timezone.utc).isoformat()
            task['verification'] = {'schema':'task-verification-v1', 'nonce':nonce,
                                    'phase':'preparing', 'started_at':now, 'updated_at':now,
                                    'approved':False, 'deployment_allowed':False}
            self._write_review_task(conn, task_id, task)

    def begin_generation(self, task_id, nonce, provider_id, test_sha256, image):
        """Reserve a one-shot synthetic/host generator call within verification intent."""
        if (not isinstance(provider_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', provider_id)
                or not isinstance(test_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', test_sha256)
                or not isinstance(image, str) or not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}', image)):
            raise ValueError('INVALID_GENERATION_BINDING')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            audit = task.get('verification', {})
            if audit.get('phase') != 'preparing' or audit.get('nonce') != nonce or 'generation' in task:
                raise ValueError('GENERATION_ALREADY_STARTED')
            digest = task.get('analysis', {}).get('source_sha256')
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('GENERATION_SOURCE_NOT_BOUND')
            revision = task.get('revision')
            root_id = revision['root_task_id'] if revision else task_id
            root = self._review_task(conn, root_id)
            family = root.get('revision_family')
            if family is None and not revision:
                family = {'schema':'revision-family-v1', 'members':[root_id],
                          'source_sha256':digest, 'test_sha256':test_sha256}
                root['revision_family'] = family
            spec = task['task']['task']
            root_spec = root['task']['task']
            if (not isinstance(spec, str) or not 1 <= len(spec) <= 4000
                    or not isinstance(root_spec, str) or not 1 <= len(root_spec) <= 4000):
                raise ValueError('GENERATION_FAMILY_CONFLICT')
            spec_digest = hashlib.sha256(spec.encode('utf-8')).hexdigest()
            root_spec_digest = hashlib.sha256(root_spec.encode('utf-8')).hexdigest()
            root_generation = root.get('generation')
            if (not isinstance(family, dict) or family.get('schema') != 'revision-family-v1'
                    or not isinstance(family.get('members'), list) or not 1 <= len(family['members']) <= 3
                    or any(not isinstance(member, str) for member in family['members'])
                    or len(set(family['members'])) != len(family['members'])
                    or family['members'][0] != root_id or family['members'][-1] != task_id
                    or root.get('analysis', {}).get('source_sha256') != digest
                    or spec_digest != root_spec_digest
                    or family.get('spec_sha256', root_spec_digest) != root_spec_digest
                    or (root_generation is not None and (not isinstance(root_generation, dict)
                        or root_generation.get('binding', {}).get('spec_sha256') != root_spec_digest))
                    or family.get('source_sha256') != digest or family.get('test_sha256') != test_sha256
                    or (revision and (revision.get('ordinal') != len(family['members'])
                        or revision.get('test_sha256') != test_sha256 or revision.get('source_sha256') != digest))):
                raise ValueError('GENERATION_FAMILY_CONFLICT')
            family = dict(family, spec_sha256=root_spec_digest)
            root['revision_family'] = family
            binding = {'schema':'generation-request-v1', 'task_id':task_id, 'nonce':nonce,
                'root_task_id':root_id, 'ordinal':len(family['members']), 'source_sha256':digest,
                'spec_sha256':spec_digest,
                'test_sha256':test_sha256, 'image':image, 'execution_policy':'bounded-arithmetic-v1',
                'provider_id':provider_id}
            task['generation'] = {'schema':'task-generation-v1', 'phase':'requested', 'binding':binding,
                'admission_required':True, 'approved':False, 'deployment_allowed':False}
            if root_id == task_id:
                task['revision_family'] = family
            else:
                self._write_review_task(conn, root_id, root)
            self._write_review_task(conn, task_id, task)
        return {'binding':dict(binding), 'task_description':spec}

    @staticmethod
    def _generation_budget(receipt):
        """Explicit units; legacy EUR and USD admissions never imply conversion."""
        if not isinstance(receipt, dict):
            raise ValueError('INVALID_GENERATION_ADMISSION')
        if receipt.get('schema') == 'generation-admission-v1':
            return ('EUR', receipt.get('budget_limit_microuros'), receipt.get('reserved_microuros'),
                    'budget_limit_microuros', 'reserved_microuros')
        if receipt.get('schema') == 'generation-admission-usd-v2':
            return ('USD', receipt.get('budget_limit_microusd'), receipt.get('reserved_microusd'),
                    'budget_limit_microusd', 'reserved_microusd')
        raise ValueError('INVALID_GENERATION_ADMISSION')

    @staticmethod
    def _generation_admission(receipt, binding, reserved_at):
        """Validate host approval metadata, not a provider invoice or signature."""
        _, limit, reserved, limit_key, reserved_key = TaskStorage._generation_budget(receipt)
        fields = {'schema','generation_authorized','binding','scope','disclosure',
                  'authorization_id','budget_period',limit_key,
                  'budget_call_limit',reserved_key,'model','max_output_tokens',
                  'expires_at','approved','deployment_allowed'}
        if (not isinstance(receipt, dict) or set(receipt) != fields
                or receipt.get('generation_authorized') is not True
                or receipt.get('binding') != binding or receipt.get('scope') != 'generate_only'
                or receipt.get('disclosure') != 'task_description_only'
                or receipt.get('approved') is not False or receipt.get('deployment_allowed') is not False
                or not isinstance(receipt.get('authorization_id'), str)
                or not re.fullmatch(r'[A-Za-z0-9_.:@/-]{1,128}', receipt['authorization_id'])
                or not isinstance(receipt.get('model'), str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}', receipt['model'])
                or any(type(receipt.get(key)) is not int for key in (
                    limit_key,'budget_call_limit',reserved_key,'max_output_tokens'))
                or not 1 <= reserved <= limit <= 10**12
                or not 1 <= receipt['budget_call_limit'] <= 100000
                or not 1 <= receipt['max_output_tokens'] <= 1500
                or receipt.get('budget_period') != reserved_at.strftime('%Y-%m')
                or not isinstance(receipt.get('expires_at'), str)):
            raise ValueError('INVALID_GENERATION_ADMISSION')
        try:
            expires = datetime.fromisoformat(receipt['expires_at'])
            if (expires.utcoffset() != timedelta(0)
                    or not reserved_at < expires <= reserved_at + timedelta(minutes=5)):
                raise ValueError('INVALID_GENERATION_ADMISSION')
        except (ValueError, TypeError, OverflowError):
            raise ValueError('INVALID_GENERATION_ADMISSION') from None

    def authorize_generation(self, task_id, nonce, receipt):
        """Atomically reserve a host-declared ceiling before the callback.

        Budgets are per database and UTC month. Committed reservations are never
        refunded here, including failed, interrupted and uncertain dispatches.
        """
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            generation, audit = task.get('generation', {}), task.get('verification', {})
            binding = generation.get('binding', {})
            if (audit.get('phase') != 'preparing' or audit.get('nonce') != nonce
                    or generation.get('phase') != 'requested' or binding.get('nonce') != nonce
                    or generation.get('admission_required') is not True or 'admission' in generation
                    or task.get('analysis', {}).get('source_sha256') != binding.get('source_sha256')
                    or hashlib.sha256(task['task']['task'].encode('utf-8')).hexdigest() != binding.get('spec_sha256')):
                raise ValueError('GENERATION_ADMISSION_CONFLICT')
            now = datetime.now(timezone.utc)
            self._generation_admission(receipt, binding, now)
            currency, limit, reserved, _, _ = self._generation_budget(receipt)
            total = calls = 0
            for other_id, encoded in conn.execute('SELECT task_id,payload FROM tasks'):
                other = json.loads(encoded)
                previous = other.get('generation')
                if previous is None or other_id == task_id:
                    continue
                if not isinstance(previous, dict) or previous.get('admission_required') is not True:
                    raise ValueError('UNACCOUNTED_GENERATION_HISTORY')
                entry = previous.get('admission')
                if entry is None:
                    previous_audit = other.get('verification', {})
                    if (previous_audit.get('phase') == 'blocked'
                            and previous_audit.get('error_stage') == 'generation_authorization'):
                        continue  # Proven rejection before any dispatch admission.
                    raise ValueError('UNACCOUNTED_GENERATION_HISTORY')
                if not isinstance(entry, dict) or set(entry) != {'receipt','reserved_at'}:
                    raise ValueError('INVALID_GENERATION_BUDGET_HISTORY')
                if hashlib.sha256(json.dumps(entry, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != previous.get('admission_sha256'):
                    raise ValueError('INVALID_GENERATION_BUDGET_HISTORY')
                try:
                    at = datetime.fromisoformat(entry['reserved_at'])
                    if at.utcoffset() != timedelta(0):
                        raise ValueError('INVALID_GENERATION_BUDGET_HISTORY')
                    self._generation_admission(entry['receipt'], previous.get('binding'), at)
                except (KeyError, TypeError, ValueError, OverflowError):
                    raise ValueError('INVALID_GENERATION_BUDGET_HISTORY') from None
                prior = entry['receipt']
                if prior['authorization_id'] == receipt['authorization_id']:
                    raise ValueError('GENERATION_AUTHORIZATION_REPLAY')
                if prior['budget_period'] == receipt['budget_period']:
                    prior_currency, prior_limit, prior_reserved, _, _ = self._generation_budget(prior)
                    if prior_currency != currency:
                        raise ValueError('GENERATION_BUDGET_CURRENCY_CONFLICT')
                    if (prior_limit != limit
                            or prior['budget_call_limit'] != receipt['budget_call_limit']):
                        raise ValueError('GENERATION_BUDGET_POLICY_CONFLICT')
                    total += prior_reserved
                    calls += 1
            if total + reserved > limit:
                raise ValueError('GENERATION_BUDGET_EXHAUSTED')
            if calls + 1 > receipt['budget_call_limit']:
                raise ValueError('GENERATION_CALL_BUDGET_EXHAUSTED')
            generation['admission'] = {'receipt':json.loads(json.dumps(receipt)), 'reserved_at':now.isoformat()}
            generation['admission_sha256'] = hashlib.sha256(json.dumps(
                generation['admission'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self._write_review_task(conn, task_id, task)
        # Only the approved execution profile is given to the trusted adapter.
        return self._generation_profile(generation)

    @staticmethod
    def _generation_profile(generation):
        receipt = generation['admission']['receipt']
        profile = {key:receipt[key] for key in (
            'model','max_output_tokens','expires_at','disclosure','scope','approved','deployment_allowed')}
        profile['admission_sha256'] = generation['admission_sha256']
        return profile

    def begin_openai_dispatch(self, request):
        """Commit a single attempt before I/O; interrupted attempts are not retried."""
        if not isinstance(request, dict) or set(request) != {'binding','task_description','admission'}:
            raise ValueError('INVALID_OPENAI_DISPATCH')
        binding = request['binding']
        if not isinstance(binding, dict) or not isinstance(binding.get('task_id'), str):
            raise ValueError('INVALID_OPENAI_DISPATCH')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, binding['task_id'])
            generation, audit = task.get('generation', {}), task.get('verification', {})
            entry = generation.get('admission')
            if (generation.get('phase') != 'requested' or audit.get('phase') != 'preparing'
                    or generation.get('admission_required') is not True
                    or audit.get('nonce') != binding.get('nonce')
                    or binding.get('provider_id') != OPENAI_GENERATOR_ID
                    or not isinstance(entry, dict) or set(entry) != {'receipt','reserved_at'}
                    or self._json_digest(entry) != generation.get('admission_sha256')
                    or 'dispatch' in generation or 'dispatch_sha256' in generation):
                raise ValueError('OPENAI_DISPATCH_CONFLICT')
            receipt = entry['receipt']
            self._generation_admission(receipt, generation.get('binding'), datetime.fromisoformat(entry['reserved_at']))
            profile = self._generation_profile(generation)
            spec = task['task']['task']
            expected = dict(binding=generation['binding'], task_description=spec, admission=profile)
            if (self._json_digest(request) != self._json_digest(expected)
                    or hashlib.sha256(spec.encode()).hexdigest() != binding.get('spec_sha256')
                    or task.get('analysis', {}).get('source_sha256') != binding.get('source_sha256')
                    or datetime.now(timezone.utc) >= datetime.fromisoformat(receipt['expires_at'])):
                raise ValueError('OPENAI_DISPATCH_CONFLICT')
            dispatch = self._openai_dispatch_profile(generation)
            dispatch['started_at'] = datetime.now(timezone.utc).isoformat()
            generation['dispatch'] = dispatch
            generation['dispatch_sha256'] = self._json_digest(dispatch)
            self._write_review_task(conn, binding['task_id'], task)
        return dict(prompt=spec, model=profile['model'], max_tokens=profile['max_output_tokens'],
                    expires_at=profile['expires_at'])

    @staticmethod
    def _json_digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    @staticmethod
    def _openai_dispatch_profile(generation):
        receipt = generation['admission']['receipt']
        return dict(provider='openai', model=receipt['model'], max_output_tokens=receipt['max_output_tokens'],
                    prompt_sha256=generation['binding']['spec_sha256'],
                    admission_sha256=generation['admission_sha256'])

    def complete_generation(self, task_id, nonce, recommendation, admission_sha256):
        if not isinstance(recommendation, str) or not recommendation.strip() or len(recommendation) > 12000:
            raise ValueError('INVALID_GENERATED_RECOMMENDATION')
        if not isinstance(admission_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', admission_sha256):
            raise ValueError('INVALID_GENERATION_ADMISSION_HASH')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            generation = task.get('generation', {})
            audit = task.get('verification', {})
            if (audit.get('phase') != 'preparing' or audit.get('nonce') != nonce
                    or generation.get('phase') != 'requested' or generation.get('binding', {}).get('nonce') != nonce
                    or generation.get('admission_required') is not True or not isinstance(generation.get('admission'), dict)
                    or generation.get('admission_sha256') != admission_sha256
                    or hashlib.sha256(json.dumps(generation.get('admission'), sort_keys=True,
                        separators=(',', ':')).encode()).hexdigest() != admission_sha256
                    or task.get('analysis', {}).get('source_sha256') != generation['binding'].get('source_sha256')
                    or hashlib.sha256(task['task']['task'].encode('utf-8')).hexdigest() != generation['binding'].get('spec_sha256')):
                raise ValueError('GENERATION_AUDIT_CONFLICT')
            if generation['binding'].get('provider_id') == OPENAI_GENERATOR_ID:
                dispatch = generation.get('dispatch')
                if (not isinstance(dispatch, dict)
                        or set(dispatch) != set(self._openai_dispatch_profile(generation)) | {'started_at'}
                        or self._json_digest(dispatch) != generation.get('dispatch_sha256')
                        or {k:v for k,v in dispatch.items() if k != 'started_at'} != self._openai_dispatch_profile(generation)):
                    raise ValueError('OPENAI_DISPATCH_CONFLICT')
            generation.update(phase='completed', response_sha256=hashlib.sha256(recommendation.encode('utf-8')).hexdigest())
            self._write_review_task(conn, task_id, task)

    def authorize_verification(self, task_id, nonce, binding, reviewer_id, authorization_id):
        """Persist a host-validated verify-only binding before dispatch, not approval."""
        fields = {'schema','nonce','task_id','candidate_sha256','test_sha256','image','scope'}
        if (not isinstance(binding, dict) or set(binding) != fields
                or binding.get('schema') != 'verification-request-v1'
                or binding.get('task_id') != task_id or binding.get('nonce') != nonce
                or binding.get('scope') != 'verify_only'
                or any(not isinstance(binding.get(key), str) or not re.fullmatch(r'[0-9a-f]{64}', binding[key])
                       for key in ('candidate_sha256','test_sha256'))
                or not isinstance(binding.get('image'), str)
                or not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}', binding['image'])
                or any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:@/-]{1,128}', value)
                       for value in (reviewer_id, authorization_id))):
            raise ValueError('INVALID_VERIFICATION_BINDING')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            audit = task.get('verification', {})
            revision = task.get('revision')
            if revision is not None and binding['test_sha256'] != revision.get('test_sha256'):
                raise ValueError('REVISION_TESTS_CHANGED')
            if audit.get('phase') != 'preparing' or audit.get('nonce') != nonce:
                raise ValueError('VERIFICATION_AUDIT_CONFLICT')
            audit.update(phase='running', binding=dict(binding), reviewer_id=reviewer_id,
                         authorization_id=authorization_id, updated_at=datetime.now(timezone.utc).isoformat())
            self._write_review_task(conn, task_id, task)

    def record_verification_resources(self, task_id, nonce, resources):
        """Persist immutable recovery handles before the isolated Docker dispatch."""
        if (not isinstance(resources, dict) or set(resources) != {'snapshot_directory','container_name'}
                or not isinstance(resources.get('snapshot_directory'), str)
                or len(resources['snapshot_directory']) > 4096
                or any(ord(char) < 32 or ord(char) == 127 for char in resources['snapshot_directory'])
                or not Path(resources['snapshot_directory']).is_absolute()
                or not re.fullmatch(r'central-ai-input-[A-Za-z0-9_-]{1,128}', Path(resources['snapshot_directory']).name)
                or not isinstance(resources.get('container_name'), str)
                or not re.fullmatch(r'central-ai-verifier-[0-9a-f]{32}', resources['container_name'])):
            raise ValueError('INVALID_VERIFICATION_RESOURCES')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            audit = task.get('verification', {})
            if (audit.get('phase') != 'running' or audit.get('nonce') != nonce
                    or 'resources' in audit):
                raise ValueError('VERIFICATION_AUDIT_CONFLICT')
            audit.update(resources=dict(resources), updated_at=datetime.now(timezone.utc).isoformat())
            self._write_review_task(conn, task_id, task)

    @staticmethod
    def review_status(database, task_ids):
        """Read durable outcomes in one RO snapshot; return counters, never content."""
        path = Path(database)
        if (not path.is_absolute() or path.resolve() != path or not path.is_file()
                or not isinstance(task_ids, tuple) or not 1 <= len(task_ids) <= 100
                or any(not isinstance(t, str) or not t for t in task_ids)
                or len(set(task_ids)) != len(task_ids)):
            raise ValueError('INVALID_REVIEW_STATUS_SCOPE')
        counts = dict(cleanup_uncertain=0, blocked=0, candidate_failed=0, pending=0, verified=0)
        seen = set()
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10) as conn:
            conn.execute('PRAGMA query_only=ON'); conn.execute('BEGIN')
            for task_id, encoded in conn.execute('SELECT task_id,payload FROM tasks'):
                task = json.loads(encoded)
                if not isinstance(task, dict):
                    raise ValueError('INVALID_VERIFICATION_AUDIT')
                if task_id in task_ids:
                    seen.add(task_id)
                try:
                    TaskStorage.check_verification_barrier([task])
                except ValueError as error:
                    if str(error) != 'VERIFICATION_DATABASE_BLOCKED':
                        raise
                    audit = task['verification']
                    name = ('cleanup_uncertain' if audit['phase'] == 'quarantined'
                            and 'resources' in audit else 'blocked')
                    counts[name] += 1
                    continue
                if task_id not in task_ids:
                    continue
                audit = task.get('verification')
                if audit is None:
                    counts['pending'] += 1
                elif audit['phase'] == 'blocked':
                    counts['blocked'] += 1
                elif audit['phase'] == 'completed':
                    outcome = audit.get('outcome')
                    TaskStorage._validated_verification_report(task_id, audit.get('nonce'), outcome)
                    if (outcome['verification_binding'] != audit.get('binding')
                            or outcome['reviewer_id'] != audit.get('reviewer_id')
                            or outcome['authorization_id'] != audit.get('authorization_id')
                            or outcome['candidate_sha256'] != audit.get('binding', {}).get('candidate_sha256')
                            or outcome['test_sha256'] != audit.get('binding', {}).get('test_sha256')
                            or outcome['quarantine_required'] is not False
                            or 'resources' not in audit
                            or task.get('status') != 'analyzed'
                            or task.get('approved') is not False or task.get('deployment_allowed') is not False):
                        raise ValueError('INVALID_VERIFICATION_AUDIT')
                    name = ('verified' if outcome['test_status'] == 'passed' else
                            'candidate_failed' if outcome['test_status'] == 'failed' else 'blocked')
                    counts[name] += 1
        if seen != set(task_ids):
            raise ValueError('REVIEW_STATUS_TASK_MISSING')
        state = next((k for k, value in counts.items() if value), 'idle')
        return dict(state=state, **counts)

    @staticmethod
    def _validated_verification_report(task_id, nonce, report):
        fields = {'task_id','candidate_sha256','test_sha256','reviewer_id','authorization_id',
                  'verification_nonce','verification_binding','test_status','tests_passed',
                  'quarantine_required','quarantine_resources','approved','deployment_allowed',
                  'completion_confirmed','execution_policy'}
        if (not isinstance(report, dict) or set(report) != fields
                or report.get('task_id') != task_id or report.get('verification_nonce') != nonce
                or report.get('approved') is not False or report.get('deployment_allowed') is not False
                or report.get('execution_policy') != 'bounded-arithmetic-v1'
                or type(report.get('completion_confirmed')) is not bool
                or report['completion_confirmed'] is not report.get('tests_passed')
                or type(report.get('tests_passed')) is not bool
                or type(report.get('quarantine_required')) is not bool
                or report.get('test_status') not in ('passed','failed','completion_unconfirmed','timeout','execution_error','cleanup_unconfirmed')
                or report['tests_passed'] is not (report['test_status'] == 'passed')
                or report['quarantine_required'] is not (report['test_status'] == 'cleanup_unconfirmed')):
            raise ValueError('INVALID_VERIFICATION_REPORT')
        encoded = json.dumps(report, allow_nan=False)
        if len(encoded.encode('utf-8')) > 32768:
            raise ValueError('VERIFICATION_REPORT_TOO_LARGE')
        return encoded

    def complete_verification(self, task_id, nonce, report):
        """Atomically store the bounded report; never promote task status."""
        encoded = self._validated_verification_report(task_id, nonce, report)
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            audit = task.get('verification', {})
            if (audit.get('phase') != 'running' or audit.get('nonce') != nonce
                    or 'resources' not in audit
                    or (report['quarantine_required'] and report['quarantine_resources'] != audit['resources'])
                    or report['verification_binding'] != audit.get('binding')
                    or report['reviewer_id'] != audit.get('reviewer_id')
                    or report['authorization_id'] != audit.get('authorization_id')
                    or report['candidate_sha256'] != audit['binding']['candidate_sha256']
                    or report['test_sha256'] != audit['binding']['test_sha256']):
                raise ValueError('VERIFICATION_AUDIT_CONFLICT')
            audit.update(phase='quarantined' if report['quarantine_required'] else 'completed',
                         outcome=json.loads(encoded), updated_at=datetime.now(timezone.utc).isoformat())
            self._write_review_task(conn, task_id, task)

    def fail_verification(self, task_id, nonce, stage, error_type):
        """Record a generic failure; any uncertainty after dispatch remains quarantined."""
        if (stage not in ('generation_authorization','generation','preparation','authorization','execution','result','persistence')
                or not isinstance(error_type, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', error_type)):
            raise ValueError('INVALID_VERIFICATION_FAILURE')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            audit = task.get('verification', {})
            if audit.get('nonce') != nonce or audit.get('phase') not in ('preparing','running'):
                raise ValueError('VERIFICATION_AUDIT_CONFLICT')
            audit.update(phase='quarantined' if audit['phase'] == 'running' else 'blocked',
                         error_stage=stage, error_type=error_type,
                         updated_at=datetime.now(timezone.utc).isoformat())
            self._write_review_task(conn, task_id, task)
