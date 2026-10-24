import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROPOSALS = BASE / "proposals"

ALLOWED = {
    "app/sec_financials.py",
    "app/sec_edgar.py",
}

def validate(path):
    path = Path(path)

    if path.parent.resolve() != PROPOSALS.resolve():
        raise ValueError("Invalid proposal directory")

    if path.is_symlink() or not path.is_file():
        raise ValueError("Invalid proposal file")

    if path.suffix != ".json":
        raise ValueError("Invalid file type")

    if path.stat().st_size > 100_000:
        raise ValueError("Proposal too large")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Invalid JSON structure")

    if data.get("target") not in ALLOWED:
        raise ValueError("Target not allowed")

    if data.get("status") != "draft":
        raise ValueError("Invalid status")

    if data.get("approved") is not False:
        raise ValueError("Proposal must not be approved")

    if data.get("production_modified") is not False:
        raise ValueError("Production modification detected")

    if not isinstance(data.get("task"), str):
        raise ValueError("Invalid task")

    if not data["task"].strip() or len(data["task"]) > 4000:
        raise ValueError("Invalid task length")

    if data.get("changes") != []:
        raise ValueError("Changes are not yet supported")

    if data.get("tests") != []:
        raise ValueError("Tests are not yet supported")

    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    data = validate(args.file)

    print("PROPOSAL_VALID")
    print("ID:", data["id"])
    print("TARGET:", data["target"])
    print("STATUS:", data["status"])


if __name__ == "__main__":
    main()
