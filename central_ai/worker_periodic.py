"""Opt-in periodic staging runner, bounded by wall clock and cycle count."""
import os
import time
from central_ai.worker_supervised import run_supervised


def run_periodic(*, enabled, database, agent, lock_path, status_path,
                 runs=3, pause=5, runner=run_supervised, sleep=time.sleep):
    if enabled != "YES":
        raise ValueError("PERIODIC_DISABLED")
    if type(runs) is not int or not 1 <= runs <= 24:
        raise ValueError("INVALID_RUNS")
    if type(pause) is not int or not 1 <= pause <= 3600:
        raise ValueError("INVALID_PAUSE")
    completed = 0
    for index in range(runs):
        result = runner(enabled="YES", database=database, agent=agent,
                        lock_path=lock_path, status_path=status_path,
                        cycles=1, interval=1, max_tasks=2)
        if result["status"] == "already_running":
            return {"state": "locked", "completed": completed}
        completed += 1
        if index + 1 < runs:
            sleep(pause)
    return {"state": "complete", "completed": completed}


def main():
    result = run_periodic(
        enabled=os.getenv("CENTRAL_PERIODIC_ENABLED", ""),
        database=os.getenv("CENTRAL_TASK_DB", ""),
        agent=os.getenv("CENTRAL_WORKER_AGENT", ""),
        lock_path=os.getenv("CENTRAL_SCHEDULER_LOCK", ""),
        status_path=os.getenv("CENTRAL_SUPERVISOR_STATUS", ""),
        runs=int(os.getenv("CENTRAL_PERIODIC_RUNS", "3")),
        pause=int(os.getenv("CENTRAL_PERIODIC_PAUSE", "5")),
    )
    print("PERIODIC_RESULT", result)


if __name__ == "__main__":
    main()
