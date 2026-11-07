"""Central AI Task Queue v0.3.

Coordination metadata only.
No task execution, approval or deployment.
"""
import json
import sqlite3
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

def utcnow():
    return datetime.now(timezone.utc)

class _BorrowedConnection:
    """Use an existing connection without committing or closing it."""

    def __init__(self, conn):
        if not isinstance(conn, sqlite3.Connection):
            raise ValueError('INVALID_CONNECTION')
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False

class TaskQueue:

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        if self.db_path.is_symlink():
            raise ValueError('INVALID_DATABASE')
        if not self.db_path.parent.is_dir():
            raise ValueError('INVALID_DIRECTORY')
        self._initialize()

    def _connect(self):
        return sqlite3.connect(str(self.db_path), timeout=10)

    def _initialize(self):
        with self._connect() as con:
            con.execute("\n                CREATE TABLE IF NOT EXISTS task_queue (\n                    task_id TEXT PRIMARY KEY,\n                    status TEXT NOT NULL\n                        CHECK(status IN ('pending','leased','done')),\n                    owner TEXT,\n                    lease_token TEXT,\n                    lease_until TEXT,\n                    version INTEGER NOT NULL DEFAULT 0\n                        CHECK(version>=0),\n                    approved INTEGER NOT NULL DEFAULT 0\n                        CHECK(approved=0),\n                    deployment_allowed INTEGER NOT NULL DEFAULT 0\n                        CHECK(deployment_allowed=0)\n                )\n            ")
            con.execute('\n                CREATE TABLE IF NOT EXISTS task_queue_audit (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    task_id TEXT NOT NULL,\n                    event TEXT NOT NULL,\n                    agent TEXT,\n                    timestamp TEXT NOT NULL\n                )\n            ')
            self._migrate_retry_columns(con)

    def _migrate_retry_columns(self, con):
        columns = {row[1] for row in con.execute('PRAGMA table_info(task_queue)')}
        if 'attempt_count' not in columns:
            con.execute('\n                ALTER TABLE task_queue\n                ADD COLUMN attempt_count INTEGER NOT NULL\n                DEFAULT 0 CHECK(attempt_count >= 0)\n            ')
        if 'retry_exhausted' not in columns:
            con.execute('\n                ALTER TABLE task_queue\n                ADD COLUMN retry_exhausted INTEGER NOT NULL\n                DEFAULT 0 CHECK(retry_exhausted IN (0,1))\n            ')

    def enqueue(self, task_id, conn=None):
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError('INVALID_TASK_ID')
        if conn is None:
            with self._connect() as own_conn:
                return self.enqueue(task_id, conn=own_conn)
        if not isinstance(conn, sqlite3.Connection):
            raise ValueError('INVALID_CONNECTION')
        con = conn
        con.execute("\n            INSERT INTO task_queue(task_id,status)\n            VALUES (?,'pending')\n        ", (task_id,))
        con.execute("\n            INSERT INTO task_queue_audit\n            (task_id,event,timestamp)\n            VALUES (?,'enqueued',?)\n        ", (task_id, utcnow().isoformat()))

    def acquire(self, task_id, agent, seconds=30):
        """Acquire one of the same three durable attempts used by acquire_next.

        A busy or exhausted task returns None without spending an attempt.
        Heartbeats and completion remain valid during the final active lease.
        """
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError('INVALID_AGENT')
        if type(seconds) is not int or not 5 <= seconds <= 3600:
            raise ValueError('INVALID_LEASE')
        now = utcnow()
        token = secrets.token_urlsafe(32)
        timestamp = now.isoformat()
        expiry = (now + timedelta(seconds=seconds)).isoformat()
        with self._connect() as con:
            # Guard, ownership change and budget reservation are one atomic
            # UPDATE, including races with acquire_next's writer transaction.
            cursor = con.execute("""
                UPDATE task_queue
                SET status='leased',
                    owner=?,
                    lease_token=?,
                    lease_until=?,
                    version=version+1,
                    attempt_count=attempt_count+1,
                    retry_exhausted=CASE
                        WHEN attempt_count+1 >= 3 THEN 1
                        ELSE 0
                    END
                WHERE task_id=?
                  AND approved=0
                  AND deployment_allowed=0
                  AND retry_exhausted=0
                  AND attempt_count < 3
                  AND (
                    (status='pending' AND owner IS NULL)
                    OR
                    (status='leased' AND lease_until <= ?)
                  )
            """, (agent, token, expiry, task_id, timestamp))
            if cursor.rowcount != 1:
                return None
            con.execute("""
                INSERT INTO task_queue_audit
                (task_id,event,agent,timestamp)
                VALUES (?,'acquired',?,?)
            """, (task_id, agent, timestamp))
        return token

    def heartbeat(self, task_id, agent, token, seconds=30):
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError('INVALID_TASK_ID')
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError('INVALID_AGENT')
        if not isinstance(token, str) or not token:
            raise ValueError('INVALID_TOKEN')
        if type(seconds) is not int or not 5 <= seconds <= 3600:
            raise ValueError('INVALID_LEASE')
        now = utcnow()
        expiry = (now + timedelta(seconds=seconds)).isoformat()
        timestamp = now.isoformat()
        with self._connect() as con:
            cursor = con.execute("\n                UPDATE task_queue\n                SET lease_until =\n                    CASE\n                        WHEN lease_until > ?\n                        THEN lease_until\n                        ELSE ?\n                    END,\n                    version=version+1\n                WHERE task_id=?\n                  AND owner=?\n                  AND lease_token=?\n                  AND status='leased'\n                  AND lease_until > ?\n                  AND approved=0\n                  AND deployment_allowed=0\n            ", (expiry, expiry, task_id, agent, token, timestamp))
            if cursor.rowcount != 1:
                raise ValueError('HEARTBEAT_REJECTED')
            con.execute("\n                INSERT INTO task_queue_audit\n                (task_id,event,agent,timestamp)\n                VALUES (?,'heartbeat',?,?)\n            ", (task_id, agent, timestamp))
        return True

    def complete(self, task_id, agent, token, conn=None):
        if not isinstance(token, str) or not token:
            raise ValueError('INVALID_TOKEN')
        now = utcnow().isoformat()
        with self._connect() if conn is None else _BorrowedConnection(conn) as con:
            cursor = con.execute("\n                UPDATE task_queue\n                SET status='done',\n                    lease_until=NULL,\n                    lease_token=NULL,\n                    version=version+1\n                WHERE task_id=?\n                  AND owner=?\n                  AND lease_token=?\n                  AND status='leased'\n                  AND lease_until > ?\n                  AND approved=0\n                  AND deployment_allowed=0\n            ", (task_id, agent, token, now))
            if cursor.rowcount != 1:
                raise ValueError('OWNERSHIP_OR_LEASE_INVALID')
            con.execute("\n                INSERT INTO task_queue_audit\n                (task_id,event,agent,timestamp)\n                VALUES (?,'completed',?,?)\n            ", (task_id, agent, now))

    def status(self, task_id):
        with self._connect() as con:
            row = con.execute('\n                SELECT task_id, status, owner,\n                       lease_until, version,\n                       approved, deployment_allowed,\n                       attempt_count, retry_exhausted\n                FROM task_queue\n                WHERE task_id=?\n                ', (task_id,)).fetchone()
        if row is None:
            raise ValueError('TASK_NOT_FOUND')
        result = dict(zip(('task_id', 'status', 'owner', 'lease_until', 'version', 'approved', 'deployment_allowed', 'attempt_count', 'retry_exhausted'), row))
        from datetime import datetime, timezone
        effective = result['status']
        if effective == 'leased' and result['retry_exhausted'] == 1 and (result['lease_until'] is not None):
            expiry = datetime.fromisoformat(result['lease_until'])
            if expiry.tzinfo is None:
                raise ValueError('INVALID_LEASE_TIMESTAMP')
            if expiry <= datetime.now(timezone.utc):
                effective = 'failed'
        result['effective_status'] = effective
        return result

    def audit(self, task_id):
        with self._connect() as con:
            rows = con.execute('\n                SELECT event,agent,timestamp\n                FROM task_queue_audit\n                WHERE task_id=?\n                ORDER BY id\n            ', (task_id,)).fetchall()
        return [{'event': e, 'agent': a, 'timestamp': t} for e, a, t in rows]

    def acquire_next(self, agent, seconds=30, require_target=False, *, allowed_task_ids=None):
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError('INVALID_AGENT')
        if type(seconds) is not int or not 5 <= seconds <= 3600:
            raise ValueError('INVALID_LEASE')
        # Scope selection inside the existing writer transaction; never acquire
        # a foreign task and release it afterward (that would spend its attempt).
        task_ids = ()
        scope_sql = ''
        if allowed_task_ids is not None:
            if (not isinstance(allowed_task_ids, (list, tuple)) or len(allowed_task_ids) > 100
                    or any(not isinstance(t, str) or not t.strip() or len(t) > 128 for t in allowed_task_ids)
                    or len(set(allowed_task_ids)) != len(allowed_task_ids)):
                raise ValueError('INVALID_TASK_SCOPE')
            task_ids = tuple(allowed_task_ids)
            if not task_ids:
                return None
            scope_sql = ' AND task_id IN (' + ','.join('?' for _ in task_ids) + ') '
        now = utcnow()
        timestamp = now.isoformat()
        expiry = (now + timedelta(seconds=seconds)).isoformat()
        token = secrets.token_urlsafe(32)
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute("\n                SELECT task_id\n                FROM task_queue\n                WHERE approved=0\n                  AND deployment_allowed=0\n                    AND retry_exhausted=0\n                    AND attempt_count < 3\n                  AND (\n                    NOT ? OR EXISTS (\n                      SELECT 1 FROM task_file_targets AS t\n                      WHERE t.task_id = task_queue.task_id\n                        AND t.approved = 0\n                        AND t.deployment_allowed = 0\n                    )\n                  )\n\n                  AND (\n                    (status='pending' AND owner IS NULL)\n                    OR\n                    (status='leased' AND lease_until <= ?)\n                  )\n                " + scope_sql + "ORDER BY task_id\n                LIMIT 1\n                ", (int(require_target), timestamp) + task_ids).fetchone()
            if row is None:
                return None
            task_id = row[0]
            cursor = con.execute("\n                UPDATE task_queue\n                SET status='leased',\n                    owner=?,\n                    lease_token=?,\n                    lease_until=?,\n                    version=version+1,\n                    attempt_count=attempt_count+1,\n                    retry_exhausted=CASE\n                        WHEN attempt_count+1 >= 3 THEN 1\n                        ELSE 0\n                    END\n                WHERE task_id=?\n                  AND approved=0\n                  AND deployment_allowed=0\n                    AND retry_exhausted=0\n                    AND attempt_count < 3\n                  AND (\n                    NOT ? OR EXISTS (\n                      SELECT 1 FROM task_file_targets AS t\n                      WHERE t.task_id = task_queue.task_id\n                        AND t.approved = 0\n                        AND t.deployment_allowed = 0\n                    )\n                  )\n\n                  AND (\n                    (status='pending' AND owner IS NULL)\n                    OR\n                    (status='leased' AND lease_until <= ?)\n                  )\n                ", (agent, token, expiry, task_id, int(require_target), timestamp))
            if cursor.rowcount != 1:
                raise RuntimeError('ACQUIRE_NEXT_CONFLICT')
            con.execute("\n                INSERT INTO task_queue_audit\n                    (task_id, event, agent, timestamp)\n                VALUES (?, 'acquired', ?, ?)\n                ", (task_id, agent, timestamp))
            return {'task_id': task_id, 'token': token}
