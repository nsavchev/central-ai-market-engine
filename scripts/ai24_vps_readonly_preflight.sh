#!/usr/bin/env bash
# AI-24 read-only production preflight. Do not alter services, secrets or volumes.
set -euo pipefail
collector_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
export GIT_OPTIONAL_LOCKS=0
cd /opt/central-ai/release-v1/market_engine_v0_9
echo "AI24_PREFLIGHT_START"
docker compose -p market_engine_v0_9 -f docker-compose.central.yml -f docker-compose.central.release.yml config --quiet
docker volume inspect market_engine_v0_9_central_ai_tasks >/dev/null
docker inspect market_engine_v0_9-central-ai-1 --format '{{.State.Status}}' | grep -qx running
docker inspect market_engine_v0_9-api-1 --format '{{.State.Status}}' | grep -qx running
docker inspect market_engine_v0_9-db-1 --format '{{.State.Status}}' | grep -qx running
docker inspect market_engine_v0_9-central-ai-1 --format '{{json .Mounts}}' | grep -q 'market_engine_v0_9_central_ai_tasks'
docker exec market_engine_v0_9-central-ai-1 python -c 'import os; assert os.getenv("CENTRAL_TASK_API_ENABLED")=="NO"; assert os.getenv("CENTRAL_TASK_DB")=="/var/lib/central-ai/tasks.sqlite"'
curl -fsS --max-time 4 http://127.0.0.1:8010/health >/dev/null
curl -fsS --max-time 4 http://127.0.0.1:8000/health >/dev/null
test -s /root/central-ai-backups/release-preupdate-20261101/central-ai-rollback-image.tar
test -s /root/central-ai-backups/release-preupdate-20261101/production-code.tar.gz
systemctl is-active --quiet central-ai-staging.timer
# These are evidence fields, not deployment or restore approval.
python3 - "$collector_path" <<'PY'
import datetime,hashlib,json,os,platform,re,subprocess,sys
from pathlib import Path

def command(args):
    return subprocess.check_output(args,stderr=subprocess.DEVNULL,timeout=10,text=True).strip()

def inspect(container,field):
    return json.loads(command(["docker","inspect",container,"--format","{{json "+field+"}}"]))

try:
    services={}
    for name in ("central-ai","api","db"):
        container="market_engine_v0_9-"+name+"-1"
        image=inspect(container,".Image")
        if not isinstance(image,str) or not re.fullmatch(r"sha256:[0-9a-f]{64}",image):
            raise ValueError("INVALID_IMAGE_ID")
        mounts=inspect(container,".Mounts")
        services[name]={
            "status":inspect(container,".State.Status"),
            "image_id":image,
            "repo_digests":json.loads(command(["docker","image","inspect",image,"--format","{{json .RepoDigests}}"])) or [],
            "configured_user":inspect(container,".Config.User"),
            "read_only_root":inspect(container,".HostConfig.ReadonlyRootfs"),
            "privileged":inspect(container,".HostConfig.Privileged"),
            "network_mode":inspect(container,".HostConfig.NetworkMode"),
            "memory_limit":inspect(container,".HostConfig.Memory"),
            "nano_cpus":inspect(container,".HostConfig.NanoCpus"),
            "mounts":[{"type":m.get("Type"),"destination":m.get("Destination"),
                       "writable":m.get("RW"),"volume_name":m.get("Name") if m.get("Type")=="volume" else None}
                      for m in mounts],
        }
    git_metadata={"sha":None,"branch":None,"dirty":None}
    git_status="unavailable"
    try:
        sha=command(["git","rev-parse","HEAD"])
        if not re.fullmatch(r"[0-9a-f]{40}",sha):
            raise ValueError("INVALID_DEPLOYED_SHA")
        branch=command(["git","branch","--show-current"])
        dirty=bool(command(["git","status","--porcelain","--untracked-files=normal"]))
        git_metadata={"sha":sha,"branch":branch,"dirty":dirty}
        git_status="available"
    except (subprocess.CalledProcessError,FileNotFoundError):
        # Git may be absent/inaccessible in an archive-based deployment.
        # Do not infer a clean tree, a source SHA or image provenance.
        pass
    configs={}
    for name in ("docker-compose.central.yml","docker-compose.central.release.yml"):
        configs[name]=hashlib.sha256(Path(name).read_bytes()).hexdigest()
    report={
        "schema":"issue90-readonly-evidence-v1",
        "timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "host_fingerprint":hashlib.sha256(platform.node().encode()).hexdigest()[:16],
        "repository_path":str(Path.cwd()),
        "git":git_metadata,
        "git_metadata_status":git_status,
        "collection_status":"collected" if git_status=="available" else "partial",
        "evidence_gaps":[] if git_status=="available" else ["deployment_git_metadata"],
        "collector_sha256":hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(),
        "compose_file_sha256":configs,
        "services":services,
        "legacy_preflight_checks_passed":True,
        "backup_files_present":True,
        "backup_restoration":"unverified",
        "sqlite_schema":"not_collected",
        "postgresql_schema":"not_collected",
        "runtime_call_graph":"not_collected",
        "audit_complete":False,
        "deployment_authorized":False,
    }
    print(json.dumps(report,sort_keys=True))
except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
    print(json.dumps({"schema":"issue90-readonly-evidence-v1","collection_failed":True,
                      "audit_complete":False,"deployment_authorized":False}))
    raise SystemExit(1)
PY
echo "AI24_READ_ONLY_VPS_PREFLIGHT_FINISHED"
