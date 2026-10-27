#!/usr/bin/env python3
"""Read-only, allowlisted VPS audit. Never executes project Python code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE = Path("/opt/central-ai")
REPO = BASE / "github-export"
RELEASE = BASE / "release-v1/market_engine_v0_9"
FILES = (
    "app/main.py", "central_ai/app.py",
    "central_ai/persistent_workflow_v05.py",
    "central_ai/workflow_controller_v03.py",
    "central_ai/task_queue.py", "central_ai/developer_task_runner.py",
)
ISSUE_URL = "https://api.github.com/repos/nsavchev/central-ai-market-engine/issues/90/comments"

def command(*args):
    try:
        p = subprocess.run(args, cwd=RELEASE, capture_output=True, text=True, timeout=15,
                           check=False, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
        if p.returncode:
            return None
        return p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None

def sha(path):
    if not path.is_file() or path.is_symlink():
        return None
    if path.stat().st_size > 2_000_000:\n        return None\n    with path.open("rb") as stream:\n        return hashlib.file_digest(stream, "sha256").hexdigest()

def report():
    commit = command("git", "-C", str(REPO), "rev-parse", "HEAD")
    if not commit or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        commit = None
    status = command("git", "-C", str(REPO), "status", "--porcelain")
    files = {}
    for item in FILES:
        local = sha(RELEASE / item)
        exported = sha(REPO / item)
        files[item] = {"release_sha256": local, "git_export_sha256": exported,
                       "matches": local == exported if local and exported else None}
    services = {}
    for service in ("api", "central-ai", "db"):
        # Docker inspect only; no secrets, environment or mounts are exported.
        out = command("docker", "inspect", "--format", "{{.State.Status}}", 
                      "market_engine_v0_9-" + service + "-1")
        services[service] = out if out in ("running", "exited", "created", "paused") else "unknown"
    sqlite_result = {"present": False}
    db = RELEASE / "central_ai/data/workflow_v04.db"
    if db.is_file() and not db.is_symlink():
        sqlite_result["present"] = True
        try:
            with sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=3) as conn:
                sqlite_result["workflow_states_rows"] = conn.execute(
                    "SELECT COUNT(*) FROM workflow_states").fetchone()[0]
                sqlite_result["workflow_states_columns"] = [
                    r[1] for r in conn.execute("PRAGMA table_info(workflow_states)")
                ]
        except sqlite3.Error:
            sqlite_result["inspection"] = "error"
    # Do not export DB connection strings, logs, host identifiers, user data, or environment.
    return {
        "schema": "vps-audit-v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git": {"commit": commit, "clean": status == "" if status is not None else None},
        "files": files, "services": services, "sqlite": sqlite_result,
        "production_database": "not inspected by this collector",
        "audit_complete": False, "deployment_authorized": False,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--post", action="store_true", help="Post allowlisted report to GitHub Issue 90")
    parser.add_argument("--token-file", type=Path,
                        default=Path.home() / ".config/central-ai-audit/github-token")
    args = parser.parse_args()
    payload = report()
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.post:
        if args.token_file.is_symlink():\n            raise SystemExit("Token file must not be a symlink")\n        st = args.token_file.stat()
        if not args.token_file.is_file() or st.st_mode & 0o077:
            raise SystemExit("Token file must not be readable by group or others")
        token = args.token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise SystemExit("Token file is empty")
        req = Request(ISSUE_URL, method="POST", data=json.dumps({
            "body": "Automated read-only VPS evidence (not a completed audit):\n\n```json\n"
                    + json.dumps(payload, indent=2, sort_keys=True) + "\n```"
        }).encode("utf-8"), headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "User-Agent": "central-ai-readonly-audit",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        })
        with urlopen(req, timeout=20) as response:
            if response.status != 201:
                raise SystemExit("GitHub report submission failed")
        print("Report submitted to GitHub Issue #90")
if __name__ == "__main__":
    main()
