import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROPOSALS = BASE / "proposals"


def inspect_proposal(path):
    from validate_proposal import validate

    data = validate(path)

    return {
        "id": data["id"],
        "target": data["target"],
        "status": data["status"],
        "task": data["task"],
        "approved": data["approved"],
        "production_modified": data["production_modified"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    result = inspect_proposal(args.file)

    print(json.dumps(
        result,
        indent=2,
        ensure_ascii=False
    ))


if __name__ == "__main__":
    main()
