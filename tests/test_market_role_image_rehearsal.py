"""Guard/cleanup fault injection; real image acceptance runs in baseline CI."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import pytest

PATH = Path(__file__).parents[1]/"scripts/market_role_image_rehearsal.py"
spec = importlib.util.spec_from_file_location("role_image_rehearsal",PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeDocker:
    def __init__(self):
        self.calls=[]
        self.containers={}
        self.labels={}
        self.network=None
        self.members={}
        self.keep_container=False

    def run(self,args,**kwargs):
        self.calls.append(args)
        output=""
        if args[0]=="ps":
            name=args[-1].removeprefix("name=^/").removesuffix("$")
            output=self.containers.get(name,"")
        elif args[0]=="inspect":
            output=json.dumps(self.labels.get(args[3],{}))
        elif args[0]=="rm":
            if not self.keep_container:
                self.containers={name:cid for name,cid in self.containers.items() if cid!=args[-1]}
        elif args[:2]==["network","ls"]:
            output=self.network or ""
        elif args[:2]==["network","inspect"]:
            output=json.dumps(self.members if ".Containers" in args[-1] else self.labels.get(args[2],{}))
        elif args[:2]==["network","rm"]:
            self.network=None
        elif args[:2]==["image","inspect"]:
            output=json.dumps({"Volumes":{"/unexpected":{}},"Env":[]})
        else:
            raise AssertionError("Unexpected test command")
        return SimpleNamespace(stdout=output,returncode=0)


def make_rehearsal(docker):
    return module.Rehearsal(docker,"sha256:"+"a"*64,"sha256:"+"b"*64,"c"*64,"-- synthetic fixture")


@pytest.mark.parametrize("image",["postgres:16","latest","sha256:invalid","x; docker rm production"])
def test_mutable_or_malformed_images_rejected_before_docker(image):
    docker=FakeDocker()
    with pytest.raises(module.RehearsalError,match="IMMUTABLE_IMAGE_IDS_REQUIRED"):
        module.Rehearsal(docker,image,"sha256:"+"b"*64,"c"*64,"")
    assert not docker.calls


def test_cleanup_never_deletes_a_container_with_wrong_owner():
    docker=FakeDocker();run=make_rehearsal(docker);run.attempted=True
    docker.containers[run.api]="foreign-container"
    docker.labels["foreign-container"]={module.LABEL:"another-run"}
    assert run.cleanup() is False
    assert not any(call[0]=="rm" for call in docker.calls)


def test_uncertain_creation_can_clean_only_reserved_owned_resources():
    docker=FakeDocker();run=make_rehearsal(docker);run.attempted=True
    docker.containers={run.api:"owned-api",run.db:"owned-db","production":"production-id"}
    docker.network="owned-network"
    for key in ("owned-api","owned-db","owned-network"):
        docker.labels[key]={module.LABEL:run.token}
    assert run.cleanup() is True
    assert docker.containers=={"production":"production-id"}
    assert [c[-1] for c in docker.calls if c[0]=="rm"]==["owned-api","owned-db"]
    assert docker.network is None


def test_unconfirmed_container_removal_and_connected_network_remain_blocked():
    docker=FakeDocker();run=make_rehearsal(docker);run.attempted=True
    docker.containers[run.db]="owned-db";docker.keep_container=True
    docker.network="owned-network";docker.members={"owned-db":{}}
    docker.labels={key:{module.LABEL:run.token} for key in ("owned-db","owned-network")}
    assert run.cleanup() is False
    assert not any(c[:2]==["network","rm"] for c in docker.calls)


def test_implicit_api_image_volumes_refused_before_resource_creation():
    docker=FakeDocker();run=make_rehearsal(docker)
    with pytest.raises(module.RehearsalError,match="API_IMAGE_IMPLICIT_VOLUMES_FORBIDDEN"):
        run.execute()
    assert run.attempted is False and run.cleanup() is True
    assert all(call[:2]==["image","inspect"] for call in docker.calls)


def test_cleanup_rejects_foreign_network_even_when_empty():
    docker=FakeDocker();run=make_rehearsal(docker);run.attempted=True
    docker.network="foreign-network"
    docker.labels["foreign-network"]={module.LABEL:"another-run"}
    assert run.cleanup() is False
    assert not any(c[:2]==["network","rm"] for c in docker.calls)


def test_image_with_unreviewed_environment_refused_without_copying_values():
    class BakedEnvDocker(FakeDocker):
        def run(self,args,**kwargs):
            self.calls.append(args)
            return SimpleNamespace(stdout=json.dumps({"Env":["SENSITIVE_TOKEN=private-fixture"],"Volumes":None}),returncode=0)
    docker=BakedEnvDocker();run=make_rehearsal(docker)
    with pytest.raises(module.RehearsalError,match="API_IMAGE_UNREVIEWED_ENVIRONMENT") as error:
        run.execute()
    assert "private-fixture" not in str(error.value)
    assert run.attempted is False


def test_compose_api_only_environment_replacement_and_rollback(tmp_path):
    """Exercise real Compose merging; config never starts containers."""
    binary = os.environ.get("COMPOSE_TEST_BINARY")
    if binary:
        command = [binary]
    elif shutil.which("docker"):
        command = ["docker", "compose"]
    else:
        pytest.skip("Compose executable required for merge acceptance")
    (tmp_path / ".env").write_text(
        "POSTGRES_PASSWORD=synthetic-admin-only\nAPI_TOKEN=synthetic-old-token\n"
    )
    base = tmp_path / "compose.yml"
    base.write_text(
        "services:\n"
        "  db:\n    image: postgres:16-alpine\n"
        "    environment:\n      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}\n"
        "  api:\n    image: synthetic-api:local\n    env_file: .env\n"
        "    environment:\n"
        "      DATABASE_URL: postgresql://owner:${POSTGRES_PASSWORD}@db/test\n"
        "    ports: ['127.0.0.1:8000:8000']\n"
        "    restart: unless-stopped\n"
    )
    # Prevent the runner's own app credentials influencing this synthetic model.
    process_env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("COMPOSE_")
        and k not in {"POSTGRES_PASSWORD", "API_TOKEN", "DATABASE_URL"}
    }

    def config(*overrides):
        args = command + ["--project-directory", str(tmp_path), "-p", "merge-test",
                          "-f", str(base)]
        for override in overrides:
            args += ["-f", str(override)]
        result = subprocess.run(
            args + ["config", "--format", "json"], env=process_env,
            capture_output=True, text=True, timeout=30, check=True,
        )
        model = json.loads(result.stdout)
        # Compose config escapes dollars for reusable output (config.go).
        for service in model["services"].values():
            service["environment"] = {
                k: v.replace("$$", "$") if isinstance(v, str) else v
                for k, v in service.get("environment", {}).items()
            }
        return model

    def write_override(path, environment):
        path.write_text(
            "services:\n  api:\n    env_file: !reset []\n"
            "    environment: !override " + json.dumps({
                k: v.replace("$", "$$") for k, v in environment.items()
            }) + "\n"
        )

    before = config()
    runtime_env = {
        "DATABASE_URL": "postgresql://runtime:synthetic-new@db/test",
        "API_TOKEN": "literal$TOKEN${OTHER}$$tail",
        "SEC_USER_AGENT": "Synthetic contact@example.invalid",
    }
    override = tmp_path / "runtime.yml"
    write_override(override, runtime_env)
    after = config(override)
    assert after["services"]["api"]["environment"] == runtime_env
    assert "POSTGRES_PASSWORD" not in after["services"]["api"]["environment"]
    assert after["services"]["db"] == before["services"]["db"]
    old_api = dict(before["services"]["api"])
    new_api = dict(after["services"]["api"])
    old_api.pop("environment"); new_api.pop("environment")
    assert new_api == old_api

    rollback = tmp_path / "rollback.yml"
    write_override(rollback, before["services"]["api"]["environment"])
    assert config(override, rollback) == before
