from pathlib import Path
from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.developer_task_runner import DeveloperTaskRunner

class DeveloperWorkerCoordinator:

    def __init__(self, db_path, agent):
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError('INVALID_AGENT')
        self.bridge = PersistentTaskBridge(db_path)
        self.targets = TaskFileTargets(db_path)
        self.targets.initialize()
        self.runner = DeveloperTaskRunner(self.bridge.queue, agent)
        self.agent = agent

    def run_once(self):
        acquired = self.bridge.queue.acquire_next(self.agent, seconds=30, require_target=True)
        if acquired is None:
            return None
        task_id = acquired['task_id']
        token = acquired['token']
        try:
            target = self.targets.get(task_id)
            if target is None:
                raise RuntimeError('TASK_TARGET_MISSING')
            if target['approved'] != 0 or target['deployment_allowed'] != 0:
                raise RuntimeError('SECURITY_FLAGS_INVALID')
            workspace = Path(target['workspace'])
            filename = target['filename']
            return self.runner.run_acquired_and_complete(
                self.bridge, task_id, token, workspace, filename
            )
        except Exception as exc:
            # Keep the original exception; audit only its type, never its text.
            try:
                self.bridge.queue.record_failure(
                    task_id, self.agent, token, type(exc).__name__
                )
            except Exception:
                pass
            raise
