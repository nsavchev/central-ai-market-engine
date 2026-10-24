import argparse
import json
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORTS = BASE / "test_reports"
PROPOSALS = BASE / "patch_proposals"

def generate(report_name):
    if Path(report_name).name != report_name:
        raise ValueError("Invalid report name")

    source = REPORTS / report_name

    if source.is_symlink() or not source.is_file():
        raise ValueError("Invalid report")

    if source.stat().st_size > 100000:
        raise ValueError("Report too large")

    data = json.loads(source.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Invalid report format")

    failed = (
        data.get("status") == "failed"
        or data.get("passed") is False
    )

    if not failed:
        raise ValueError("No failed test to review")

    error = str(data.get("stderr") or data.get("error") or "")

    if "AssertionError" in error:
        suggestion = (
            "Inspect the failing assertion and compare "
            "expected versus actual results. "
            "Check validation logic without weakening "
            "security requirements."
        )
    elif "ModuleNotFoundError" in error:
        suggestion = (
            "Check dependency declarations and the "
            "isolated Python environment."
        )
    else:
        suggestion = (
            "Reproduce the failure in an isolated test "
            "environment and inspect the full traceback."
        )

    proposal = {
        "id": uuid.uuid4().hex,
        "suite": data.get("suite"),
        "error": error[:4000],
        "suggestion": suggestion,
        "status": "review_only",
        "ai_generated": False,
        "approved": False,
        "automatic_fix_allowed": False,
        "deployment_allowed": False,
        "production_modified": False
    }

    if PROPOSALS.is_symlink():
        raise ValueError("Invalid proposal directory")

    PROPOSALS.mkdir(parents=True, exist_ok=True, mode=0o700)

    path = PROPOSALS / f"{proposal['id']}.json"

    with path.open("x", encoding="utf-8") as f:
        json.dump(proposal, f, indent=2)

    print("PATCH_PROPOSAL_CREATED")
    print("REPORT:", path)
    print("PRODUCTION_UNCHANGED")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    generate(args.report)

if __name__ == "__main__":
    main()
