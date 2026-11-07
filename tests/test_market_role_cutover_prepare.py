"""Prepare-only acceptance using real Compose and synthetic Docker metadata."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

PATH = Path(__file__).parents[1] / "scripts/market_role_cutover_prepare.py"
spec = importlib.util.spec_from_file_location("cutover_prepare", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    binary = os.environ.get("COMPOSE_TEST_BINARY")
    if binary:
        compose = [binary]
    elif shutil.which("docker"):
        compose = ["docker", "compose"]
    else:
        pytest.skip("Compose executable required")
    tmp_path.chmod(0o700)
    base = tmp_path / "compose.yml"
    (tmp_path / ".env").write_text(
        "POSTGRES_PASSWORD=synthetic-admin\n"
        "API_TOKEN='literal$TOKEN${OTHER}$$tail'\nSEC_USER_AGENT=Fixture\n"
    )
    base.write_text(
        "services:\n  db:\n    image: postgres:16-alpine\n"
        "    environment:\n      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}\n"
        "  api:\n    build: .\n    restart: unless-stopped\n"
        "    env_file: .env\n    environment:\n"
        "      DATABASE_URL: postgresql+psycopg://owner:${POSTGRES_PASSWORD}@db/test\n"
        "    ports: ['127.0.0.1:8000:8000']\n"
    )
    # Keep test credentials independent from the CI runner's app environment.
    for key in module.APP_KEYS | {"COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES"}:
        monkeypatch.delenv(key, raising=False)
    image = "sha256:" + "a" * 64
    actual = {
        "Id": "synthetic-api", "Image": image, "State": {"Running": True},
        "Config": {"Labels": {
            "com.docker.compose.service": "api",
            "com.docker.compose.project.config_files": str(base),
            "com.docker.compose.project.working_dir": str(tmp_path),
            "com.docker.compose.project": "synthetic-project",
        }, "Env": ["PATH=/usr/bin", "POSTGRES_PASSWORD=synthetic-admin",
                   "API_TOKEN=literal$TOKEN${OTHER}$$tail", "SEC_USER_AGENT=Fixture",
                   "DATABASE_URL=postgresql+psycopg://owner:synthetic-admin@db/test"]},
        "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"},
                       "PortBindings": {"8000/tcp": [
                           {"HostIp": "127.0.0.1", "HostPort": "8000"}]}},
    }
    image_config = {"Config": {"Env": ["PATH=/usr/bin"], "Volumes": None}}
    calls = []

    def read_only_command(*args):
        calls.append(args)
        if args[:2] == ("docker", "inspect"):
            return json.dumps([actual])
        if args[:3] == ("docker", "image", "inspect"):
            return json.dumps([image_config])
        if args[:2] == ("docker", "ps"):
            return "synthetic-db\nsynthetic-api\nsynthetic-central\n"
        assert args[:2] == ("docker", "compose") and args[-3:] == ("config", "--format", "json")
        result = subprocess.run(compose + list(args[2:]), capture_output=True,
                                text=True, timeout=30, check=True)
        return result.stdout

    monkeypatch.setattr(module, "command", read_only_command)
    return tmp_path, base, actual, image_config, calls


def test_prepares_private_review_files_without_applying_sql_or_restarting(fixture):
    root, base, actual, _, calls = fixture
    result = module.prepare("synthetic-api", base, root)
    directory = Path(result["review_directory"])
    assert directory.stat().st_mode & 0o777 == 0o700
    assert {p.name for p in directory.iterdir()} == {
        "runtime.compose.yml", "rollback.compose.yml", "role.sql", "review.json"}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())
    runtime = (directory / "runtime.compose.yml").read_text()
    assert "synthetic-admin" not in runtime and "POSTGRES_PASSWORD" not in runtime
    assert "literal$$TOKEN$${OTHER}$$$$tail" in runtime
    sql = (directory / "role.sql").read_text()
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE" in sql
    assert "GRANT ALL" not in sql and "ALTER DEFAULT PRIVILEGES" not in sql
    assert "CREATE ROLE" in sql and "UPDATE ON TABLE public.instruments" not in sql
    assert "synthetic-admin" in (directory / "rollback.compose.yml").read_text()
    state = json.loads((directory / "review.json").read_text())
    assert state["api_image"] == actual["Image"] and state["applied"] is False
    assert len(state["source_file_sha256"]) == 2
    assert result["role_sql_executed"] is False and result["services_restarted"] is False
    assert not any("exec" in call or "up" in call or "run" in call for call in calls)


@pytest.mark.parametrize("failure", ["env_drift", "baked_secret", "unknown_app_key", "multiple_files", "port_drift"])
def test_refuses_unreviewed_state_before_creating_private_files(fixture, failure):
    root, base, actual, image, _ = fixture
    if failure == "env_drift":
        actual["Config"]["Env"][-1] += "changed"
    elif failure == "baked_secret":
        image["Config"]["Env"].append("POSTGRES_PASSWORD=private-value")
    elif failure == "unknown_app_key":
        with (root / ".env").open("a") as stream:
            stream.write("UNREVIEWED_SECRET=private-value\n")
    elif failure == "multiple_files":
        actual["Config"]["Labels"]["com.docker.compose.project.config_files"] += ",other.yml"
    else:
        actual["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(module.PreparationError) as error:
        module.prepare("synthetic-api", base, root)
    assert "private-value" not in str(error.value)
    assert not list(root.glob("market-role-review-*"))


def test_failed_merge_removes_only_the_new_review_directory(fixture, monkeypatch):
    root, base, _, _, _ = fixture
    original = module.decode_config
    count = 0

    def broken_override(model):
        nonlocal count
        count += 1
        result = original(model)
        if count > 1:
            result["services"]["db"]["image"] = "unexpected"
        return result

    monkeypatch.setattr(module, "decode_config", broken_override)
    with pytest.raises(module.PreparationError, match="OTHER_CONFIGURATION"):
        module.prepare("synthetic-api", base, root)
    assert not list(root.glob("market-role-review-*"))
    assert base.exists() and (root / ".env").exists()
