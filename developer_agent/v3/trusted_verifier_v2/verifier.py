import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]

ALLOWED = {
    "workflow": "developer_agent/v3/tests/test_workflow.py",
}

def verify(suite):
    if suite not in ALLOWED:
        raise ValueError("SUITE_NOT_ALLOWED")

    target = BASE / ALLOWED[suite]

    if target.is_symlink() or not target.is_file():
        raise ValueError("INVALID_TEST_TARGET")

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            str(target.parent),
            "-p",
            target.name,
            "-v",
        ],
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
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "approved": False,
        "deployment_allowed": False,
        "verified_by": "trusted_verifier_v2",
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
