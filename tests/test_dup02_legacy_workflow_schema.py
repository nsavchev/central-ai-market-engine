import sqlite3
import pytest
from central_ai.persistent_workflow_v05 import PersistentWorkflowV05

def legacy(path, approved=0):
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE workflow_states (
          task_id TEXT PRIMARY KEY, stage TEXT NOT NULL, attempts INTEGER NOT NULL,
          approved INTEGER NOT NULL, deployment_allowed INTEGER NOT NULL,
          history TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        con.execute("INSERT INTO workflow_states VALUES (?, 'test', 1, ?, 0, '[]', 'now')",
                    ("legacy-task", approved))

def test_known_v04_schema_is_upgraded_without_losing_task(tmp_path):
    db=tmp_path/"state.sqlite"
    legacy(db)
    workflow=PersistentWorkflowV05(db)
    state, version=workflow.restore("legacy-task")
    assert (state["stage"], state["attempts"], version)==("test",1,0)
    assert state["approved"] is False
    assert state["deployment_allowed"] is False
    with sqlite3.connect(db) as con:
        assert "version" in {row[1] for row in con.execute("PRAGMA table_info(workflow_states)")}
        assert con.execute("SELECT count(*) FROM workflow_states").fetchone()[0]==1

def test_reject_unsafe_legacy_flags_without_migrating(tmp_path):
    db=tmp_path/"unsafe.sqlite"
    legacy(db, approved=1)
    with pytest.raises(ValueError, match="STORED_SECURITY_VIOLATION"):
        PersistentWorkflowV05(db)
    with sqlite3.connect(db) as con:
        assert "version" not in {row[1] for row in con.execute("PRAGMA table_info(workflow_states)")}

def test_unknown_schema_fails_closed(tmp_path):
    db=tmp_path/"unknown.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE workflow_states (task_id TEXT PRIMARY KEY)")
    with pytest.raises(ValueError, match="UNKNOWN_WORKFLOW_SCHEMA"):
        PersistentWorkflowV05(db)


@pytest.mark.parametrize("column", ["unexpected TEXT", "version TEXT NOT NULL DEFAULT '0'", "version INTEGER"])
def test_unknown_schema_additions_fail_closed(tmp_path, column):
    db = tmp_path / "unknown_extra.sqlite"
    legacy(db)
    with sqlite3.connect(db) as con:
        con.execute("ALTER TABLE workflow_states ADD COLUMN " + column)
    with pytest.raises(ValueError, match="UNKNOWN_WORKFLOW_SCHEMA"):
        PersistentWorkflowV05(db)


@pytest.mark.parametrize("field,value", [
    ("stage", "not-a-stage"),
    ("attempts", -1),
    ("history", "not-json"),
    ("history", "{}"),
])
def test_invalid_legacy_rows_rejected_before_migration(tmp_path, field, value):
    db = tmp_path / "corrupted.sqlite"
    legacy(db)
    with sqlite3.connect(db) as con:
        con.execute(f"UPDATE workflow_states SET {field}=?", (value,))
    with pytest.raises(ValueError, match="INVALID_STORED_WORKFLOW"):
        PersistentWorkflowV05(db)
    with sqlite3.connect(db) as con:
        assert "version" not in {row[1] for row in con.execute("PRAGMA table_info(workflow_states)")}


def test_migrate_multiple_rows_and_reopen_idempotently(tmp_path):
    db = tmp_path / "multiple.sqlite"
    legacy(db)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO workflow_states VALUES (?, 'plan', 0, 0, 0, '[]', 'now')",
            ("second-task",),
        )
    for _ in range(2):
        workflow = PersistentWorkflowV05(db)
        assert workflow.restore("legacy-task")[1] == 0
        assert workflow.restore("second-task")[1] == 0
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM workflow_states").fetchone()[0] == 2
