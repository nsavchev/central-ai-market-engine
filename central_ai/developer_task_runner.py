from central_ai.heartbeat_worker import HeartbeatWorker
from central_ai.task_queue import TaskQueue


class DeveloperTaskRunner:
    def __init__(self, queue: TaskQueue, agent: str):
        if not isinstance(queue, TaskQueue):
            raise ValueError("INVALID_QUEUE")
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError("INVALID_AGENT")

        self.queue = queue
        self.agent = agent

    def run_check(self, task_id: str):
        token = self.queue.acquire(
            task_id,
            self.agent,
            seconds=30,
        )

        if token is None:
            return {"status": "not_acquired"}

        worker = HeartbeatWorker(
            self.queue,
            task_id,
            self.agent,
            token,
            lease_seconds=30,
            interval_seconds=10,
        )

        worker.start()

        try:
            if not worker.healthy:
                raise RuntimeError("HEARTBEAT_UNHEALTHY")

            result = {
                "task_id": task_id,
                "agent": self.agent,
                "status": "checked",
            }

            if not worker.healthy:
                raise RuntimeError("LEASE_LOST")

            self.verify_ownership(task_id, token)
            return result

        finally:
            worker.stop()


    def verify_ownership(self, task_id, token):
        try:
            self.queue.heartbeat(
                task_id,
                self.agent,
                token,
                seconds=30,
            )
        except ValueError as exc:
            raise RuntimeError("LEASE_LOST") from exc
        return True


    def run_analysis(self, task_id, workspace, filename):
        from central_ai.read_only_analyzer import ReadOnlyAnalyzer

        token = self.queue.acquire(
            task_id, self.agent, seconds=30
        )
        if token is None:
            return {"status": "not_acquired"}

        worker = HeartbeatWorker(
            self.queue,
            task_id,
            self.agent,
            token,
            lease_seconds=30,
            interval_seconds=10,
        )

        try:
            worker.start()

            if not worker.healthy:
                raise RuntimeError("HEARTBEAT_UNHEALTHY")

            result = ReadOnlyAnalyzer(workspace).analyze(filename)

            if not worker.healthy:
                raise RuntimeError("LEASE_LOST")

            self.verify_ownership(task_id, token)

            return {
                "task_id": task_id,
                "agent": self.agent,
                "status": "analyzed",
                "analysis": result,
            }
        finally:
            worker.stop()


    def run_and_complete(self, bridge, task_id, workspace, filename):
        from central_ai.persistent_bridge import PersistentTaskBridge
        from central_ai.read_only_analyzer import ReadOnlyAnalyzer

        if not isinstance(bridge, PersistentTaskBridge):
            raise ValueError("INVALID_BRIDGE")

        if bridge.queue.db_path.resolve() != self.queue.db_path.resolve():
            raise ValueError("DATABASE_MISMATCH")

        token = self.queue.acquire(
            task_id, self.agent, seconds=30
        )

        if token is None:
            return {"status": "not_acquired"}

        worker = HeartbeatWorker(
            self.queue,
            task_id,
            self.agent,
            token,
            lease_seconds=30,
            interval_seconds=10,
        )

        try:
            worker.start()

            if not worker.healthy:
                raise RuntimeError("HEARTBEAT_UNHEALTHY")

            analysis = ReadOnlyAnalyzer(workspace).analyze(filename)

            if not worker.healthy:
                raise RuntimeError("LEASE_LOST")

            self.verify_ownership(task_id, token)

            if not worker.healthy:
                raise RuntimeError("LEASE_LOST")

            return bridge.complete_analysis(
                task_id,
                self.agent,
                token,
                analysis,
            )
        finally:
            worker.stop()


    def run_acquired_and_complete(
        self, bridge, task_id, token, workspace, filename
    ):
        from central_ai.persistent_bridge import PersistentTaskBridge
        from central_ai.read_only_analyzer import ReadOnlyAnalyzer

        if not isinstance(bridge, PersistentTaskBridge):
            raise ValueError("INVALID_BRIDGE")

        if bridge.queue.db_path.resolve() != self.queue.db_path.resolve():
            raise ValueError("DATABASE_MISMATCH")

        if not isinstance(token, str) or not token:
            raise ValueError("INVALID_TOKEN")

        worker = HeartbeatWorker(
            self.queue,
            task_id,
            self.agent,
            token,
            lease_seconds=30,
            interval_seconds=10,
        )

        try:
            self.verify_ownership(task_id, token)
            worker.start()

            if not worker.healthy:
                raise RuntimeError("HEARTBEAT_UNHEALTHY")

            analysis = ReadOnlyAnalyzer(workspace).analyze(filename)

            if not worker.healthy:
                raise RuntimeError("LEASE_LOST")

            self.verify_ownership(task_id, token)

            if not worker.healthy:
                raise RuntimeError("LEASE_LOST")

            return bridge.complete_analysis(
                task_id,
                self.agent,
                token,
                analysis,
            )
        finally:
            worker.stop()
