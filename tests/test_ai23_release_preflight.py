import pytest
from central_ai.release_preflight import inspect_release

def test_preflight_disabled(tmp_path):
    with pytest.raises(ValueError,match="PREFLIGHT_DISABLED"):
        inspect_release(enabled="",release_root=str(tmp_path))

def test_missing_config_denied(tmp_path):
    with pytest.raises(ValueError,match="RELEASE_CONFIG_MISSING"):
        inspect_release(enabled="YES",release_root=str(tmp_path))

def test_accepted_release_config(tmp_path):
    (tmp_path/"docker-compose.central.release.yml").write_text(
        "services:\n  central-ai:\n    environment:\n      CENTRAL_TASK_API_ENABLED: NO\n"
        "      CENTRAL_TASK_DB: /var/lib/central-ai/tasks.sqlite\n"
        "volumes:\n  central_ai_tasks:\n    external: true\n"
        "    name: market_engine_v0_9_central_ai_tasks\n")
    result=inspect_release(enabled="YES",release_root=str(tmp_path))
    assert result["deployed"] is False
    assert result["production_modified"] is False
