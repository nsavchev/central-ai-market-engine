"""Supervised bounded scheduler process. No autonomous deployment or broker access."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from central_ai.worker_scheduler import scheduled_cycles


def run_supervised(*, enabled, database, agent, lock_path, status_path,
                   cycles=3, interval=5, max_tasks=10, scheduler=scheduled_cycles):
    if enabled != "YES":
        raise ValueError("SERVICE_DISABLED")
    db = Path(database)
    status = Path(status_path)
    if not db.is_absolute() or not db.is_file() or db.is_symlink():
        raise ValueError("TASK_DB_UNAVAILABLE")
    if not status.is_absolute() or status.parent != db.parent or status.is_symlink():
        raise ValueError("INVALID_STATUS_PATH")
    # Do not record task content, tokens, or credentials.
    def write_state(state, **fields):
        record = {"at": datetime.now(timezone.utc).isoformat(), "state": state, **fields}
        tmp = status.with_suffix(".tmp")
        if tmp.is_symlink():
            raise ValueError("INVALID_STATUS_TEMP")
        with tmp.open("w") as f:
            json.dump(record, f)
            f.write("\n")
        os.replace(tmp, status)
    write_state("starting")
    try:
        result = scheduler(enabled="YES",database=str(db),agent=agent,
                           lock_path=lock_path,cycles=cycles,interval=interval,
                           max_tasks=max_tasks)
        write_state("complete" if result["status"] == "complete" else "already_running",
                    cycles=result["cycles"], processed=result.get("processed", 0))
        return result
    except Exception as exc:
        write_state("failed", error_type=type(exc).__name__)
        raise


def main():
    result = run_supervised(
        enabled=os.getenv("CENTRAL_SUPERVISED_SERVICE_ENABLED", ""),
        database=os.getenv("CENTRAL_TASK_DB", ""),
        agent=os.getenv("CENTRAL_WORKER_AGENT", ""),
        lock_path=os.getenv("CENTRAL_SCHEDULER_LOCK", ""),
        status_path=os.getenv("CENTRAL_SUPERVISOR_STATUS", ""),
        cycles=int(os.getenv("CENTRAL_SCHEDULER_CYCLES", "3")),
        interval=int(os.getenv("CENTRAL_SCHEDULER_INTERVAL", "5")),
        max_tasks=int(os.getenv("CENTRAL_WORKER_MAX_TASKS", "10")),
    )
    print("SUPERVISED_RESULT", result)


if __name__ == "__main__":
    main()
