"""Guard/cleanup fault injection; real image acceptance runs in baseline CI."""
import importlib.util
import json
from pathlib import Path
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
