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
OUTPUT = BASE / "ast_candidates"
TARGET = PROJECT / "app/sec_financials.py"

def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def main():
    files = sorted(PROPOSALS.glob("proposal_*.json"))
    if not files:
        raise SystemExit("No proposals found")

    source = files[-1]
    if source.is_symlink():
        raise SystemExit("Symlink rejected")

    data = json.loads(source.read_text("utf-8"))

    if data.get("target") != "app/sec_financials.py":
        raise SystemExit("Target not allowed")

    if data.get("approved") is not False:
        raise SystemExit("Unexpected approval state")

    if data.get("deployment_allowed") is not False:
        raise SystemExit("Deployment must be disabled")

    answers = data.get("ai_recommendations")
    if not isinstance(answers, list) or len(answers) != 1:
        raise SystemExit("Expected one AI response")

    if not isinstance(answers[0], str):
        raise SystemExit("Invalid response")

    blocks = re.findall(
        r"```python\s*\n(.*?)```",
        answers[0],
        flags=re.DOTALL | re.IGNORECASE
    )

    if len(blocks) != 1:
        raise SystemExit("Expected one Python block")

    proposed = blocks[0]
    proposed_tree = ast.parse(proposed)

    if TARGET.is_symlink() or not TARGET.is_file():
        raise SystemExit("Invalid target")

    original = TARGET.read_text("utf-8")
    original_tree = ast.parse(original)

    original_lines = original.splitlines(keepends=True)
    proposed_lines = proposed.splitlines(keepends=True)

    original_functions = {
        node.name: node
        for node in original_tree.body
        if isinstance(node, ast.FunctionDef)
    }

    proposed_functions = {
        node.name: node
        for node in proposed_tree.body
        if isinstance(node, ast.FunctionDef)
    }

    if set(proposed_functions) != {
        "parse_date_safe", "select_fact"
    }:
        raise SystemExit("Unexpected proposed functions")

    if "select_fact" not in original_functions:
        raise SystemExit("Original select_fact missing")

    if "sec_to_financials" not in original_functions:
        raise SystemExit("Protected function missing")

    old_node = original_functions["select_fact"]
    new_node = proposed_functions["select_fact"]
    helper_node = proposed_functions["parse_date_safe"]

    replacement = "".join(
        proposed_lines[new_node.lineno-1:new_node.end_lineno]
    )

    helper = "".join(
        proposed_lines[helper_node.lineno-1:helper_node.end_lineno]
    )

    start = min(
        [old_node.lineno] +
        [d.lineno for d in old_node.decorator_list]
    ) - 1

    end = old_node.end_lineno

    candidate_lines = (
        original_lines[:start]
        + [helper + "\n\n", replacement + "\n"]
        + original_lines[end:]
    )

    candidate = "".join(candidate_lines)
    ast.parse(candidate)

    candidate_tree = ast.parse(candidate)

    def get_function(tree, name):
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.dump(node, include_attributes=False)
        raise ValueError("Missing function: " + name)

    if get_function(
        original_tree, "sec_to_financials"
    ) != get_function(
        candidate_tree, "sec_to_financials"
    ):
        raise SystemExit("Protected function changed")

    proposal_id = data.get("id")
    if not isinstance(proposal_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,100}", proposal_id
    ):
        raise SystemExit("Invalid proposal ID")

    OUTPUT.mkdir(mode=0o700, parents=True, exist_ok=True)

    candidate_path = OUTPUT / f"candidate_{proposal_id}.py"
    diff_path = OUTPUT / f"candidate_{proposal_id}.diff"
    report_path = OUTPUT / f"candidate_{proposal_id}.json"

    paths = (candidate_path, diff_path, report_path)
    if any(p.exists() or p.is_symlink() for p in paths):
        raise SystemExit("Candidate already exists")

    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        candidate.splitlines(keepends=True),
        fromfile="original/sec_financials.py",
        tofile="candidate/sec_financials.py"
    ))

    report = {
        "proposal_id": proposal_id,
        "original_sha256": sha256(original),
        "candidate_sha256": sha256(candidate),
        "protected_function_preserved": True,
        "approved": False,
        "deployment_allowed": False,
        "test_status": "not_run",
        "review_status": "pending",
    }

    for path, content in (
        (candidate_path, candidate),
        (diff_path, diff),
        (report_path, json.dumps(report, indent=2))
    ):
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)

    print("AST_CANDIDATE_CREATED")
    print("CANDIDATE:", candidate_path)
    print("DIFF:", diff_path)
    print("DIFF_LINES:", len(diff.splitlines()))
    print("PROTECTED_FUNCTION_PRESERVED: True")
    print("TEST_STATUS: not_run")
    print("DEPLOYMENT_ALLOWED: False")
    print("PRODUCTION_UNCHANGED")

if __name__ == "__main__":
    main()
