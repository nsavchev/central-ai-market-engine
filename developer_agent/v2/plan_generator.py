import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
REVIEWS = BASE / "reviews"
PLANS = BASE / "plans"

def main():
    reviews = sorted(REVIEWS.glob("review_*.json"))
    if not reviews:
        raise SystemExit("No AI reviews found")

    review_path = reviews[-1]

    if review_path.is_symlink():
        raise SystemExit("Symlink review rejected")

    review = json.loads(
        review_path.read_text(encoding="utf-8")
    )

    if not isinstance(review, dict):
        raise SystemExit("Invalid review format")

    analysis = review.get("analysis")
    if not isinstance(analysis, str) or not analysis.strip():
        raise SystemExit("Missing AI analysis")

    if review.get("production_modified") is not False:
        raise SystemExit("Production safety check failed")

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )
    plan_id = f"{timestamp}_{uuid.uuid4().hex[:12]}"

    plan = {
        "id": plan_id,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_review": review_path.name,
        "status": "draft",
        "approved": False,
        "production_modified": False,
        "target": "app/sec_financials.py",
        "analysis": analysis,
        "proposed_changes": [],
        "tests": [],
        "review_required": True,
        "deployment_allowed": False
    }

    PLANS.mkdir(mode=0o700, parents=True, exist_ok=True)

    output = PLANS / f"plan_{plan_id}.json"

    fd = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600
    )

    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    print("PLAN_CREATED")
    print("FILE:", output)
    print("STATUS:", plan["status"])
    print("APPROVED:", plan["approved"])
    print("DEPLOYMENT_ALLOWED:", plan["deployment_allowed"])
    print("PRODUCTION_UNCHANGED")

if __name__ == "__main__":
    main()
