"""P0 contract: one scheduling/queue chain; candidate test work stays opt-in."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "central_ai"


def _imports(module):
    tree = ast.parse((ROOT / module).read_text("utf-8"))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_scheduler_ownership_is_single_direction():
    assert "central_ai.worker_batch" in _imports("worker_scheduler.py")
    assert "central_ai.worker_scheduler" in _imports("worker_supervised.py")
    assert "central_ai.developer_worker_coordinator" in _imports("worker_batch.py")
    assert "central_ai.developer_task_runner" in _imports("developer_worker_coordinator.py")
    assert "central_ai.task_queue" in _imports("persistent_bridge.py")


def test_verifier_is_separate_from_worker_scheduler():
    for module in ("worker_batch.py", "worker_scheduler.py", "worker_supervised.py"):
        imports = _imports(module)
        assert "central_ai.isolated_functional_verifier" not in imports
        assert "central_ai.verified_review_pipeline" not in imports


def test_verified_pipeline_still_requires_explicit_opt_in():
    tree = ast.parse((ROOT / "verified_review_pipeline.py").read_text("utf-8"))
    funcs = [x for x in tree.body if isinstance(x, ast.FunctionDef)]
    assert any(f.name == "prepare_and_verify" for f in funcs)
    code = (ROOT / "verified_review_pipeline.py").read_text("utf-8")
    assert 'if enabled != "YES":' in code
    assert '"deployment_allowed": False' in code
