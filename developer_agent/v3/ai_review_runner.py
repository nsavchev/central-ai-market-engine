import json
import os
import sys
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
REVIEWS = BASE / "ai_reviews"
REPORTS = BASE / "test_reports"
API_URL = "http://127.0.0.1:8010/ask"

def main():
    token = os.environ.get("CENTRAL_API_TOKEN")
    if not token:
        raise SystemExit("TOKEN_MISSING")

    files = [
        p for p in REVIEWS.glob("*.json")
        if p.is_file() and not p.is_symlink()
    ]

    if not files:
        raise SystemExit("NO_REVIEW_RECORDS")

    pending = []
    for path in files:
        if path.stat().st_size > 100000:
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("review_status") == "pending_ai_review":
            pending.append((path, record))

    if not pending:
        raise SystemExit("NO_PENDING_REVIEWS")

    if len(pending) != 1:
        raise SystemExit("EXPECTED_ONE_PENDING_REVIEW")

    path, record = pending[0]
    report_name = record["source_report"]

    if Path(report_name).name != report_name:
        raise SystemExit("INVALID_REPORT_NAME")

    report_path = REPORTS / report_name

    if report_path.is_symlink() or not report_path.is_file():
        raise SystemExit("INVALID_REPORT")

    if report_path.stat().st_size > 100000:
        raise SystemExit("REPORT_TOO_LARGE")

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    prompt = (
        "Review this simulated test failure. "
        "Explain the likely cause and recommend safe tests. "
        "Do not execute code, modify files, approve patches, "
        "or authorize deployment. "
        "Preserve validate_source and existing permissions.\n\n"
        + json.dumps(report)
    )

    with httpx.Client(
        timeout=120,
        trust_env=False,
        follow_redirects=False
    ) as client:
        response = client.post(
            API_URL,
            headers={"X-API-Token": token},
            json={
                "mode": "single",
                "providers": ["openai"],
                "prompt": prompt,
                "max_tokens": 1200
            }
        )
        response.raise_for_status()
        result = response.json()["results"][0]

    if result.get("status") != "ok":
        raise SystemExit("AI_REVIEW_FAILED")

    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise SystemExit("EMPTY_AI_REVIEW")

    record["ai_analysis"] = answer
    record["review_status"] = "review_completed"
    record["approved"] = False
    record["automatic_fix_allowed"] = False
    record["deployment_allowed"] = False

    temp = path.with_suffix(".tmp")
    with temp.open("x", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    os.replace(temp, path)

    print("AI_REVIEW_SAVED")
    print("STATUS:", record["review_status"])
    print("ANALYSIS_LENGTH:", len(answer))
    print("AUTOMATIC_FIX_ALLOWED: False")
    print("DEPLOYMENT_ALLOWED: False")

if __name__ == "__main__":
    main()
