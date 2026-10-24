import ast
import difflib
import hashlib
import json
import os
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent.parent
PROPOSALS = BASE / "code_proposals"
OUTPUT = BASE / "patches"

ALLOWED_TARGET = "app/sec_financials.py"


def main():
    files = sorted(PROPOSALS.glob("proposal_*.json"))
    if not files:
        raise SystemExit("No proposals found")

    proposal_path = files[-1]
    if proposal_path.is_symlink():
        raise SystemExit("Symlink proposal rejected")

    data = json.loads(proposal_path.read_text("utf-8"))

    if data.get("target") != ALLOWED_TARGET:
        raise SystemExit("Target not allowed")

    if data.get("approved") is not False:
        raise SystemExit("Unexpected approval state")

    if data.get("deployment_allowed") is not False:
        raise SystemExit("Deployment must remain disabled")

    if data.get("production_modified") is not False:
        raise SystemExit("Production modification flag invalid")

    answers = data.get("ai_recommendations", [])
    if not isinstance(answers, list) or len(answers) != 1:
        raise SystemExit("Expected exactly one AI response")

    if not isinstance(answers[0], str):
        raise SystemExit("Invalid AI response")

    blocks = re.findall(
        r"```python\s*\n(.*?)```",
        answers[0],
        flags=re.DOTALL | re.IGNORECASE
    )

    if len(blocks) != 1:
        raise SystemExit("Expected exactly one Python block")

    code = blocks[0]
    tree = ast.parse(code)

    functions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    if functions.count("select_fact") != 1:
        raise SystemExit("Exactly one select_fact required")

    if functions.count("parse_date_safe") != 1:
        raise SystemExit("Exactly one parse_date_safe required")

    target = PROJECT / ALLOWED_TARGET
    if target.is_symlink() or not target.is_file():
        raise SystemExit("Invalid production target")

    original = target.read_text("utf-8")

    original_hash = hashlib.sha256(
        original.encode("utf-8")
    ).hexdigest()

    patch = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        code.splitlines(keepends=True),
        fromfile="production/sec_financials.py",
        tofile="proposal/sec_financials.py",
    ))

    OUTPUT.mkdir(mode=0o700, parents=True, exist_ok=True)

    proposal_id = data.get("id")
    if not isinstance(proposal_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,100}", proposal_id
    ):
        raise SystemExit("Invalid proposal ID")

    result = {
        "proposal_id": proposal_id,
        "target": ALLOWED_TARGET,
        "original_sha256": original_hash,
        "generated_functions": functions,
        "patch": patch,
        "approved": False,
        "deployment_allowed": False,
        "test_status": "not_run",
        "review_status": "pending",
        "production_modified": False,
    }

    destination = OUTPUT / f"patch_{proposal_id}.json"

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(destination, flags, 0o600)

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)

    print("SAFE_PATCH_CREATED")
    print("FILE:", destination)
    print("FUNCTIONS:", functions)
    print("PATCH_LINES:", len(patch.splitlines()))
    print("ORIGINAL_SHA256:", original_hash)
    print("DEPLOYMENT_ALLOWED: False")
    print("TEST_STATUS: not_run")
    print("PRODUCTION_UNCHANGED")


if __name__ == "__main__":
    main()
