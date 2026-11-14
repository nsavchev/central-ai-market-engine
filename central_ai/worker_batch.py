"""Bounded, explicitly enabled read-only task processing; no deployment or trades."""
import os
import time
from pathlib import Path
from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator


def run_batch(*, enabled, database, agent, max_tasks=10, idle_checks=3, idle_seconds=1, sleep=time.sleep, coordinator=None, review_handler=None):
    if enabled != "YES":
        raise ValueError("WORKER_DISABLED")
    path = Path(database)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("TASK_DB_UNAVAILABLE")
    if not isinstance(agent, str) or not agent.strip() or len(agent) > 64:
        raise ValueError("INVALID_AGENT")
    if type(max_tasks) is not int or not 1 <= max_tasks <= 100:
        raise ValueError("INVALID_MAX_TASKS")
    if type(idle_checks) is not int or not 1 <= idle_checks <= 20:
        raise ValueError("INVALID_IDLE_CHECKS")
    if type(idle_seconds) is not int or not 1 <= idle_seconds <= 30:
        raise ValueError("INVALID_IDLE_SECONDS")
    if coordinator is not None and review_handler is not None:
        raise ValueError('AMBIGUOUS_REVIEW_COORDINATOR')
    worker = coordinator or (DeveloperWorkerCoordinator(path, agent) if review_handler is None else
                            DeveloperWorkerCoordinator(path, agent, review_handler=review_handler))
    processed = 0
    idle = 0
    while processed < max_tasks and idle < idle_checks:
        result = worker.run_once()
        if result is None:
            idle += 1
            if idle < idle_checks:
                sleep(idle_seconds)
        else:
            processed += 1
            idle = 0
    return {"processed": processed, "idle_checks": idle, "max_tasks": max_tasks}


def main():
    result = run_batch(
        enabled=os.environ.get("CENTRAL_WORKER_BATCH_ENABLED", ""),
        database=os.environ.get("CENTRAL_TASK_DB", ""),
        agent=os.environ.get("CENTRAL_WORKER_AGENT", ""),
        max_tasks=int(os.environ.get("CENTRAL_WORKER_MAX_TASKS", "10")),
        idle_checks=int(os.environ.get("CENTRAL_WORKER_IDLE_CHECKS", "3")),
        idle_seconds=int(os.environ.get("CENTRAL_WORKER_IDLE_SECONDS", "1")),
    )
    print("BATCH_COMPLETE", result)


if __name__ == "__main__":
    main()
