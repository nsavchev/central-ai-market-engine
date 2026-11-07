"""Opt-in bounded scheduler for read-only analysis. No deploy or trading."""
import fcntl
import os
import time
from pathlib import Path
from central_ai.worker_batch import run_batch

def scheduled_cycles(*, enabled, database, agent, lock_path, cycles=3, interval=5, max_tasks=10, sleep=time.sleep, batch=run_batch, review_handler=None):
    if enabled != "YES":
        raise ValueError("SCHEDULER_DISABLED")
    if type(cycles) is not int or not 1 <= cycles <= 24:
        raise ValueError("INVALID_CYCLES")
    if type(interval) is not int or not 1 <= interval <= 3600:
        raise ValueError("INVALID_INTERVAL")
    db = Path(database)
    lock = Path(lock_path)
    if not db.is_absolute() or not db.is_file() or db.is_symlink():
        raise ValueError("TASK_DB_UNAVAILABLE")
    if not lock.is_absolute() or lock.is_symlink() or lock.parent != db.parent:
        raise ValueError("INVALID_LOCK_PATH")
    with lock.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "already_running", "cycles": 0}
        completed = 0
        total = 0
        for i in range(cycles):
            options = {} if review_handler is None else {'review_handler': review_handler}
            result = batch(enabled="YES", database=str(db), agent=agent, max_tasks=max_tasks, **options)
            completed += 1
            total += result["processed"]
            if i + 1 < cycles:
                sleep(interval)
        return {"status": "complete", "cycles": completed, "processed": total}

def main():
    database = os.environ.get("CENTRAL_TASK_DB", "")
    result = scheduled_cycles(
        enabled=os.environ.get("CENTRAL_SCHEDULER_ENABLED", ""),
        database=database,
        agent=os.environ.get("CENTRAL_WORKER_AGENT", ""),
        lock_path=os.environ.get("CENTRAL_SCHEDULER_LOCK", ""),
        cycles=int(os.environ.get("CENTRAL_SCHEDULER_CYCLES", "3")),
        interval=int(os.environ.get("CENTRAL_SCHEDULER_INTERVAL", "5")),
        max_tasks=int(os.environ.get("CENTRAL_WORKER_MAX_TASKS", "10")),
    )
    print("SCHEDULER_RESULT", result)

if __name__ == "__main__":
    main()
