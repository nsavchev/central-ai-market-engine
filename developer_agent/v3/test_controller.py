import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORTS = BASE / "test_reports"

ALLOWED = {
    "workflow": [
        sys.executable, "-m",
        "py_compile",
        "developer_agent/v3/workflow.py"
    ],
    "planner": [
        sys.executable, "-m",
        "py_compile",
        "developer_agent/v3/ai_planner.py"
    ],
    "bridge": [
        sys.executable, "-m",
        "py_compile",
        "developer_agent/v3/plan_bridge.py"
    ],
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=sorted(ALLOWED),
        required=True
    )
    args = parser.parse_args()

    command = ALLOWED[args.suite]

    result = subprocess.run(
        command,
        cwd=BASE.parent.parent,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    report = {
        "suite": args.suite,
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "approved": False,
        "deployment_allowed": False,
    }

    if REPORTS.is_symlink():
        raise RuntimeError("Invalid reports directory")

    REPORTS.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700
    )

    output = REPORTS / f"{uuid.uuid4().hex}.json"

    with output.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("TEST_PASSED" if report["passed"] else "TEST_FAILED")
    print("SUITE:", args.suite)
    print("REPORT:", output)
    print("DEPLOYMENT_ALLOWED: False")

    if not report["passed"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
