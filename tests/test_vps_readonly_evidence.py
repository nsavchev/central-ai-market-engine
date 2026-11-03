"""Run only the embedded collector with synthetic subprocess responses; no VPS."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/ai24_vps_readonly_preflight.sh"


def run_collector(tmp_path,monkeypatch,fail=False):
    for name in ("docker-compose.central.yml","docker-compose.central.release.yml"):
        (tmp_path/name).write_text("synthetic compose")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys,"argv",["collector",str(SCRIPT)])
    calls=[]
    def fake_command(args,**kwargs):
        calls.append(args)
        if fail:
            raise subprocess.CalledProcessError(1,args,output="SENSITIVE_FAILURE_OUTPUT")
        if args[:2]==["git","rev-parse"]:return "a"*40
        if args[:2]==["git","branch"]:return "ci-fixture"
        if args[:2]==["git","status"]:return "?? confidential-filename"
        if args[:3]==["docker","image","inspect"]:return "[]"
        fields={
            ".Image":"sha256:"+"b"*64,".State.Status":"running",".Config.User":"10001",
            ".HostConfig.ReadonlyRootfs":True,".HostConfig.Privileged":False,
            ".HostConfig.NetworkMode":"none",".HostConfig.Memory":268435456,
            ".HostConfig.NanoCpus":1000000000,
            ".Mounts":[{"Type":"bind","Source":"/SENSITIVE_HOST_PATH","Destination":"/var/lib/central-ai","RW":True},
                       {"Type":"volume","Name":"ci-volume","Source":"/PRIVATE_VOLUME_PATH","Destination":"/ci-volume","RW":False}],
        }
        field=args[-1].removeprefix("{{json ").removesuffix("}}")
        return json.dumps(fields[field])
    monkeypatch.setattr(subprocess,"check_output",fake_command)
    code=SCRIPT.read_text().split("<<'PY'\n",1)[1].split("\nPY\n",1)[0]
    exec(compile(code,"<readonly-collector>","exec"),{})
    return calls


def test_readonly_report_redacts_sensitive_fields(tmp_path,monkeypatch,capsys):
    calls=run_collector(tmp_path,monkeypatch)
    raw=capsys.readouterr().out
    report=json.loads(raw)
    assert "SENSITIVE_HOST_PATH" not in raw and "PRIVATE_VOLUME_PATH" not in raw
    assert "confidential-filename" not in raw
    assert report["git"]=={"sha":"a"*40,"branch":"ci-fixture","dirty":True}
    assert report["backup_files_present"] is True
    assert report["backup_restoration"]=="unverified"
    assert report["audit_complete"] is False and report["deployment_authorized"] is False
    assert report["sqlite_schema"]==report["postgresql_schema"]=="not_collected"
    assert report["collector_sha256"]==hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert all(args[0]=="git" or args[:2]==["docker","inspect"] or args[:3]==["docker","image","inspect"] for args in calls)


def test_collection_failure_never_leaks_command_output(tmp_path,monkeypatch,capsys):
    with pytest.raises(SystemExit) as error:
        run_collector(tmp_path,monkeypatch,fail=True)
    assert error.value.code==1
    raw=capsys.readouterr().out
    assert "SENSITIVE_FAILURE_OUTPUT" not in raw
    report=json.loads(raw)
    assert report["collection_failed"] is True and report["deployment_authorized"] is False
