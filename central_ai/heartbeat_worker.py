import threading

from central_ai.task_queue import TaskQueue


class HeartbeatWorker:
    def __init__(
        self,
        queue: TaskQueue,
        task_id: str,
        agent: str,
        token: str,
        lease_seconds: int = 30,
        interval_seconds: float = 10,
    ):
        if not isinstance(queue, TaskQueue):
            raise ValueError("INVALID_QUEUE")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("INVALID_TASK_ID")
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError("INVALID_AGENT")
        if not isinstance(token, str) or not token:
            raise ValueError("INVALID_TOKEN")
        if type(lease_seconds) is not int or not 5 <= lease_seconds <= 3600:
            raise ValueError("INVALID_LEASE")
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not 0 < interval_seconds < lease_seconds / 2
        ):
            raise ValueError("INVALID_INTERVAL")

        self.queue = queue
        self.task_id = task_id
        self.agent = agent
        self.token = token
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds

        self._stop_event = threading.Event()
        self._thread = None
        self.error = None

    def _run(self):
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.queue.heartbeat(
                    self.task_id,
                    self.agent,
                    self.token,
                    seconds=self.lease_seconds,
                )
            except Exception as exc:
                self.error = exc
                self._stop_event.set()
                return

    def start(self):
        if self._thread is not None:
            raise RuntimeError("WORKER_ALREADY_STARTED")

        self._thread = threading.Thread(
            target=self._run,
            name="heartbeat-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

    @property
    def healthy(self):
        return (
            self._thread is not None
            and self._thread.is_alive()
            and not self._stop_event.is_set()
            and self.error is None
        )
