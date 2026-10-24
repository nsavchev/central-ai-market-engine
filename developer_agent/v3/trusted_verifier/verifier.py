import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]

ALLOWED = {
    "workflow": "developer_agent/v3/workflow.py",
    "planner": "developer_agent/v3/ai_planner.py",
    "bridge": "developer_agent/v3/plan_bridge.py",
}

def verify(suite):
    if suite not in ALLOWED:
        raise ValueError("SUITE_NOT_ALLOWED")

    target = BASE / ALLOWED[suite]

    if not target.is_file() or target.is_symlink():
        raise ValueError("INVALID_TARGET")

    result = subprocess.run(
        [sys.executable, "-B", "-m", "py_compile", str(target)],
        cwd=BASE,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    return {
        "suite": suite,
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "approved": False,
        "deployment_allowed": False,
        "verified_by": "trusted_verifier_v1",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=sorted(ALLOWED),
        required=True,
    )
    args = parser.parse_args()

    report = verify(args.suite)
    print(json.dumps(report, indent=2))

    if not report["passed"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
