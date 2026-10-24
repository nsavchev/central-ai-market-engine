import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORTS = BASE / "test_reports"

def analyze(report_path):
    path = Path(report_path).resolve()
    root = REPORTS.resolve()

    if root not in path.parents:
        raise ValueError("Report outside allowed directory")

    if not path.is_file() or path.is_symlink():
        raise ValueError("Invalid report")

    if path.stat().st_size > 100000:
        raise ValueError("Report too large")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Invalid report format")

    passed = data.get("passed")

    if type(passed) is not bool:
        raise ValueError("Invalid test status")

    result = {
        "suite": data.get("suite"),
        "status": "passed" if passed else "failed",
        "needs_fix": not passed,
        "error": str(data.get("stderr", ""))[:4000],
        "attempts_allowed": 3,
        "automatic_fix_allowed": False,
        "deployment_allowed": False,
    }

    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    result = analyze(args.report)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
