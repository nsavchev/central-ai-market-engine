"""Explicit, single-pass developer analysis worker. No deployment or trade actions."""
import os
from pathlib import Path
from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator


def main():
    if os.environ.get("CENTRAL_WORKER_ONCE_ENABLED") != "YES":
        raise SystemExit("WORKER_DISABLED")
    database = os.environ.get("CENTRAL_TASK_DB", "")
    if not database or not Path(database).is_absolute() or not Path(database).is_file():
        raise SystemExit("TASK_DB_UNAVAILABLE")
    agent = os.environ.get("CENTRAL_WORKER_AGENT", "")
    if not agent or len(agent) > 64:
        raise SystemExit("INVALID_AGENT")
    worker = DeveloperWorkerCoordinator(database, agent)
    result = worker.run_once()
    print("NO_ELIGIBLE_TASK" if result is None else "ANALYSIS_COMPLETED")


if __name__ == "__main__":
    main()
