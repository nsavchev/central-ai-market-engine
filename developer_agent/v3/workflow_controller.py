import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORTS = BASE / "test_reports"

def verify_report(name):
    # Fail closed until report provenance is verified.
    raise ValueError("UNVERIFIED_REPORT_BLOCKED")
    if (
        Path(name).name != name
        or not name.endswith(".json")
    ):
        raise ValueError("INVALID_REPORT_NAME")

    if REPORTS.is_symlink():
        raise ValueError("INVALID_REPORT_DIRECTORY")

    path = REPORTS / name

    if path.is_symlink() or not path.is_file():
        raise ValueError("INVALID_REPORT_FILE")

    if path.stat().st_size > 100000:
        raise ValueError("REPORT_TOO_LARGE")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("INVALID_REPORT_FORMAT")

    passed = data.get("passed") is True
    deployment_blocked = data.get("deployment_allowed") is False
    approval_blocked = data.get("approved") is False

    return {
        "suite": data.get("suite"),
        "tests_passed": passed,
        "checks_passed": (
            passed and deployment_blocked and approval_blocked
        ),
        "deployment_allowed": False,
        "approved": False,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    result = verify_report(args.report)
    print(json.dumps(result, indent=2))

    if not result["checks_passed"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
