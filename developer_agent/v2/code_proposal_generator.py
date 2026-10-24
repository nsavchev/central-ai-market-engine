import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORTS = BASE.parent / "reports"
OUTPUT = BASE / "code_proposals"

def main():
    reports = sorted(REPORTS.glob("analysis_*.json"))

    if not reports:
        raise SystemExit("No AI analysis found")

    source = reports[-1]

    if source.is_symlink():
        raise SystemExit("Symlink rejected")

    data = json.loads(source.read_text(encoding="utf-8"))
    results = data.get("result", {}).get("results", [])

    answers = [
        r["answer"]
        for r in results
        if isinstance(r, dict)
        and r.get("status") == "ok"
        and isinstance(r.get("answer"), str)
        and r["answer"].strip()
    ]

    if not answers:
        raise SystemExit("No successful AI response")

    proposal = {
        "id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_analysis": source.name,
        "target": "app/sec_financials.py",
        "status": "draft",
        "approved": False,
        "production_modified": False,
        "deployment_allowed": False,
        "ai_recommendations": answers,
        "patch": None,
        "tests": [],
        "test_status": "not_run",
        "review_status": "pending"
    }

    OUTPUT.mkdir(parents=True, exist_ok=True, mode=0o700)

    path = OUTPUT / f"proposal_{proposal['id']}.json"

    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600
    )

    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    print("CODE_PROPOSAL_CREATED")
    print("FILE:", path)
    print("AI_RESPONSES:", len(answers))
    print("PATCH:", proposal["patch"])
    print("TEST_STATUS:", proposal["test_status"])
    print("DEPLOYMENT_ALLOWED:", proposal["deployment_allowed"])
    print("PRODUCTION_UNCHANGED")

if __name__ == "__main__":
    main()
