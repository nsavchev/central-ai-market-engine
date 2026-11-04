"""Central AI Task Storage v0.2."""

import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


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
            if 'verification' in task:
                raise ValueError('VERIFICATION_ALREADY_STARTED')
            for (encoded,) in conn.execute('SELECT payload FROM tasks'):
                existing = json.loads(encoded)
                if 'verification' not in existing:
                    continue
                audit = existing['verification']
                if (not isinstance(audit, dict) or audit.get('schema') != 'task-verification-v1'
                        or audit.get('phase') not in ('preparing','running','completed','blocked','quarantined')
                        or audit.get('approved') is not False or audit.get('deployment_allowed') is not False):
                    raise ValueError('INVALID_VERIFICATION_AUDIT')
                if audit['phase'] in ('preparing','running','quarantined'):
                    raise ValueError('VERIFICATION_DATABASE_BLOCKED')
            now = datetime.now(timezone.utc).isoformat()
            task['verification'] = {'schema':'task-verification-v1', 'nonce':nonce,
                                    'phase':'preparing', 'started_at':now, 'updated_at':now,
                                    'approved':False, 'deployment_allowed':False}
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
            if audit.get('phase') != 'preparing' or audit.get('nonce') != nonce:
                raise ValueError('VERIFICATION_AUDIT_CONFLICT')
            audit.update(phase='running', binding=dict(binding), reviewer_id=reviewer_id,
                         authorization_id=authorization_id, updated_at=datetime.now(timezone.utc).isoformat())
            self._write_review_task(conn, task_id, task)

    def complete_verification(self, task_id, nonce, report):
        """Atomically store only the bounded pipeline report; never promote task status."""
        fields = {'task_id','candidate_sha256','test_sha256','reviewer_id','authorization_id',
                  'verification_nonce','verification_binding','test_status','tests_passed',
                  'quarantine_required','quarantine_resources','approved','deployment_allowed'}
        if (not isinstance(report, dict) or set(report) != fields
                or report.get('task_id') != task_id or report.get('verification_nonce') != nonce
                or report.get('approved') is not False or report.get('deployment_allowed') is not False
                or type(report.get('tests_passed')) is not bool
                or type(report.get('quarantine_required')) is not bool
                or report.get('test_status') not in ('passed','failed','timeout','cleanup_unconfirmed')
                or report['tests_passed'] is not (report['test_status'] == 'passed')
                or report['quarantine_required'] is not (report['test_status'] == 'cleanup_unconfirmed')):
            raise ValueError('INVALID_VERIFICATION_REPORT')
        encoded = json.dumps(report, allow_nan=False)
        if len(encoded.encode('utf-8')) > 32768:
            raise ValueError('VERIFICATION_REPORT_TOO_LARGE')
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = self._review_task(conn, task_id)
            audit = task.get('verification', {})
            if (audit.get('phase') != 'running' or audit.get('nonce') != nonce
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
        if (stage not in ('preparation','authorization','execution','result','persistence')
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
