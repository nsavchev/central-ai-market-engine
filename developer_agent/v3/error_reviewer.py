import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORTS = BASE / "test_reports"

def review(report_name):
    if Path(report_name).name != report_name:
        raise ValueError("Invalid report name")

    path = REPORTS / report_name

    if path.is_symlink() or not path.is_file():
        raise ValueError("Invalid report")

    if path.stat().st_size > 100000:
        raise ValueError("Report too large")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Invalid report format")

    failed = (
        data.get("status") == "failed"
        or data.get("passed") is False
    )

    error = str(data.get("stderr") or data.get("error") or "")

    if failed:
        if "AssertionError" in error:
            diagnosis = "A test assertion failed"
            recommendation = (
                "Inspect the assertion, expected result, "
                "actual result and validation logic."
            )
        elif "ModuleNotFoundError" in error:
            diagnosis = "Missing Python dependency"
            recommendation = (
                "Verify the Python environment and "
                "declared dependencies."
            )
        else:
            diagnosis = "Unclassified test failure"
            recommendation = (
                "Inspect the complete test logs and "
                "reproduce the failure in isolation."
            )
    else:
        diagnosis = "No failure detected"
        recommendation = "No changes required"

    return {
        "suite": data.get("suite"),
        "needs_fix": failed,
        "diagnosis": diagnosis,
        "recommendation": recommendation,
        "ai_generated": False,
        "automatic_fix_allowed": False,
        "approved": False,
        "deployment_allowed": False
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    result = review(args.report)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
