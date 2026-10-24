import argparse
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROPOSALS = BASE / "proposals"

ALLOWED = {
    "app/sec_financials.py",
    "app/sec_edgar.py",
}

def create_proposal(task, target):
    if target not in ALLOWED:
        raise ValueError("Target is not allowed")

    if not task.strip() or len(task) > 4000:
        raise ValueError("Invalid task")

    PROPOSALS.mkdir(mode=0o700, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )
    proposal_id = (
        timestamp + "_" + secrets.token_hex(8)
    )

    proposal = {
        "id": proposal_id,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "draft",
        "target": target,
        "task": task,
        "changes": [],
        "tests": [],
        "approved": False,
        "production_modified": False,
    }

    path = PROPOSALS / f"{proposal_id}.json"

    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )

    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(
            proposal,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    path = create_proposal(
        args.task,
        args.target,
    )

    print("PROPOSAL_CREATED")
    print(path)


if __name__ == "__main__":
    main()
