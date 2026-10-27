import importlib.util
from pathlib import Path
import sqlite3
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/vps_readonly_audit.py"
spec = importlib.util.spec_from_file_location("vps_readonly_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def test_report_redacts_and_does_not_expose_secrets(tmp_path, monkeypatch):
    repo, release = tmp_path / "repo", tmp_path / "release"
    repo.mkdir()
    release.mkdir()
    monkeypatch.setattr(audit, "REPO", repo)
    monkeypatch.setattr(audit, "RELEASE", release)
    monkeypatch.setattr(audit, "FILES", ("app/main.py",))
    monkeypatch.setattr(audit, "command", lambda *a: (
        "a" * 40 if "rev-parse" in a else
        "" if "status" in a else "running"))
    for base in (repo, release):
        (base / "app").mkdir()
        (base / "app/main.py").write_text("safe")
    result = audit.report()
    assert result["git"]["clean"] is True
    assert result["files"]["app/main.py"]["matches"] is True
    assert result["audit_complete"] is False
    assert result["deployment_authorized"] is False
    assert "token" not in str(result).lower()
    assert "secret" not in str(result).lower()

def test_sqlite_schema_counts_only(tmp_path, monkeypatch):
    repo, release = tmp_path / "repo", tmp_path / "release"
    repo.mkdir()
    (release / "central_ai/data").mkdir(parents=True)
    db = release / "central_ai/data/workflow_v04.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE workflow_states (task_id TEXT, version INTEGER)")
        con.execute("INSERT INTO workflow_states VALUES ('private-user-content', 0)")
    monkeypatch.setattr(audit, "REPO", repo)
    monkeypatch.setattr(audit, "RELEASE", release)
    monkeypatch.setattr(audit, "FILES", ())
    monkeypatch.setattr(audit, "command", lambda *a: None)
    result = audit.report()
    assert result["sqlite"]["workflow_states_rows"] == 1
    assert "private-user-content" not in str(result)

def test_missing_or_oversize_file_returns_no_hash(tmp_path):
    assert audit.sha(tmp_path / "missing") is None
    p = tmp_path / "large.py"
    with p.open("wb") as stream:
        stream.truncate(2_000_001)
    assert audit.sha(p) is None
    link = tmp_path / "link"
    link.symlink_to(p)
    assert audit.sha(link) is None
