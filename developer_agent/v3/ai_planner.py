import argparse
import json
import os
import sys
from pathlib import Path

import httpx

API_URL = "http://127.0.0.1:8010/ask"
OUTPUT = Path("developer_agent/v3/plans")


def generate_plan(task):
    token = os.getenv("CENTRAL_API_TOKEN")
    if not token:
        raise RuntimeError("CENTRAL_API_TOKEN missing")

    prompt = (
        "You are a software development planner. "
        "Create a safe, structured development plan. "
        "Do not execute code or request production deployment. "
        "Preserve existing security and source permissions. "
        "Return implementation steps and test requirements.\n\n"
        f"Task: {task}"
    )

    with httpx.Client(
        timeout=120,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.post(
            API_URL,
            headers={"X-API-Token": token},
            json={
                "mode": "single",
                "providers": ["openai"],
                "prompt": prompt,
                "max_tokens": 1500,
            },
        )
        response.raise_for_status()
        data = response.json()

    results = data.get("results", [])
    if not isinstance(results, list) or len(results) != 1:
        raise RuntimeError("Invalid AI response")

    result = results[0]
    if (
        not isinstance(result, dict)
        or result.get("status") != "ok"
        or not isinstance(result.get("answer"), str)
        or not result["answer"].strip()
    ):
        raise RuntimeError("AI planning failed")

    return {
        "task": task,
        "stage": "plan",
        "plan": result["answer"],
        "approved": False,
        "deployment_allowed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    args = parser.parse_args()

    if not args.task.strip() or len(args.task) > 4000:
        raise SystemExit("Invalid task")

    result = generate_plan(args.task)

    if OUTPUT.is_symlink():
        raise SystemExit("Invalid output directory")

    OUTPUT.mkdir(parents=True, exist_ok=True, mode=0o700)

    import uuid
    path = OUTPUT / f"plan_{uuid.uuid4().hex}.json"

    with path.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("AI_PLAN_CREATED")
    print(path)
    print("DEPLOYMENT_ALLOWED: False")


if __name__ == "__main__":
    main()
