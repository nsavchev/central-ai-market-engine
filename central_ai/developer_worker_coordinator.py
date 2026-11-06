from pathlib import Path
from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.developer_task_runner import DeveloperTaskRunner

class DeveloperWorkerCoordinator:

    @staticmethod
    def configured_review_handler(*, enabled, config_path, database):
        """Trusted dependency setup stays at the coordinator/pipeline boundary."""
        from central_ai.verified_review_pipeline import load_worker_review_config
        return load_worker_review_config(enabled=enabled, config_path=config_path, database=database)

    def __init__(self, db_path, agent, *, review_handler=None):
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError('INVALID_AGENT')
        if review_handler is not None and (
                not callable(review_handler) or not callable(getattr(review_handler, 'next_task_id', None))
                or not callable(getattr(review_handler, 'accepts', None))
                or Path(getattr(review_handler, 'database', '')).resolve() != Path(db_path).resolve()):
            raise ValueError('INVALID_WORKER_REVIEW_HANDLER')
        self.review_handler = review_handler
        self.bridge = PersistentTaskBridge(db_path)
        self.targets = TaskFileTargets(db_path)
        self.targets.initialize()
        self.runner = DeveloperTaskRunner(self.bridge.queue, agent)
        self.agent = agent

    def run_once(self):
        if self.review_handler is not None:
            pending = self.review_handler.next_task_id()
            if pending is not None:
                return {'task_id': pending, 'status': 'reviewed',
                        'verification': self.review_handler(pending)}
        acquired = self.bridge.queue.acquire_next(self.agent, seconds=30, require_target=True)
        if acquired is None:
            return None
        task_id = acquired['task_id']
        token = acquired['token']
        target = self.targets.get(task_id)
        if target is None:
            raise RuntimeError('TASK_TARGET_MISSING')
        if target['approved'] != 0 or target['deployment_allowed'] != 0:
            raise RuntimeError('SECURITY_FLAGS_INVALID')
        workspace = Path(target['workspace'])
        filename = target['filename']
        result = self.runner.run_acquired_and_complete(self.bridge, task_id, token, workspace, filename)
        if self.review_handler is not None and self.review_handler.accepts(task_id):
            result = dict(result, verification=self.review_handler(task_id))
        return result
