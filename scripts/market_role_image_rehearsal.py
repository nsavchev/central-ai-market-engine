#!/usr/bin/env python3
"""Disposable legacy API-image/DB-role acceptance. Never changes deployed services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time

LABEL = "central-ai.role-rehearsal"
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")

API_CHECK = r'''
import asyncio, hashlib, json, os, sys
from pathlib import Path
stage = "manifest"
try:
    root = Path("/srv/app")
    items = [[p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()]
             for p in sorted(root.rglob("*.py")) if p.is_file()]
    digest = hashlib.sha256(json.dumps(items,separators=(",",":")).encode()).hexdigest()
    assert items and digest == os.environ["REHEARSAL_MANIFEST"]
    assert not Path("/srv/.env").exists() and not list(root.rglob(".env*"))
    from sqlalchemy import text, event
    from sqlalchemy.exc import DBAPIError
    from app import main
    from app.db import engine, SessionLocal, Instrument, DailyBar
    from datetime import date
    stage = "independent_login"
    with engine.connect() as c:
        row = c.execute(text("SELECT current_user,session_user,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        assert tuple(row) == ("ci_runtime","ci_runtime",False,False,False,False,False)
        assert not c.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')"))
    ddl = []
    def watch(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split(None,1)[0].upper() in ("CREATE","ALTER","DROP","TRUNCATE"):
            ddl.append(True)
    event.listen(engine,"before_cursor_execute",watch)
    stage = "startup_and_http"
    async def http_checks():
        import httpx
        async with main.lifespan(main.app):
            assert not ddl
            event.remove(engine,"before_cursor_execute",watch)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url="http://fixture") as client:
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/paper/account")).status_code == 401
                headers = {"X-API-Token":os.environ["API_TOKEN"]}
                assert (await client.get("/paper/account",headers=headers)).status_code == 200
                fill = await client.post("/paper/trades",headers=headers,json={"symbol":"CI","side":"BUY","quantity":1,"price":10,"fee":0})
                assert fill.status_code == 200 and fill.json()["mode"] == "SIMULATION_ONLY"
                item = {"symbol":"CI","period_end":"2023-12-31","period_type":"FY","currency":"USD","source":"manual","revenue":"100","net_income":"10","total_assets":"200","shareholders_equity":"120"}
                assert (await client.post("/fundamentals/history/import",headers=headers,json=[item])).status_code == 200
                item["revenue"] = "120"
                assert (await client.post("/fundamentals/history/import",headers=headers,json=[item])).status_code == 200
                history = await client.get("/fundamentals/history/CI?source=manual&currency=USD&years=2",headers=headers)
                assert history.status_code == 200 and history.json()["records"] == 1
    asyncio.run(http_checks())
    stage = "orm_dml"
    with SessionLocal.begin() as db:
        ins = Instrument(symbol="CI",exchange="SMART",currency="USD",sec_type="STK",primary_exchange="")
        db.add(ins); db.flush()
        bar = DailyBar(instrument_id=ins.id,day=date(2023,1,1),open=10,high=12,low=9,close=11,volume=100,source="manual")
        db.add(bar); db.flush(); bar.close = 12
    engine.dispose()
    with engine.connect() as c:
        for table in ("instruments","daily_bars","financial_snapshots","paper_accounts","paper_trades"):
            assert c.scalar(text("SELECT count(*) FROM public."+table)) == 1
    stage = "denied_operations"
    denied = ["DELETE FROM public."+t for t in ("instruments","daily_bars","financial_snapshots","paper_accounts","paper_trades")]
    denied += ["CREATE TABLE public.ci_denied(id integer)","ALTER TABLE public.paper_accounts ADD COLUMN ci_denied integer","TRUNCATE public.paper_trades","ALTER SEQUENCE public.paper_trades_id_seq RESTART WITH 100","SELECT setval('public.paper_trades_id_seq',100,false)","CREATE ROLE ci_denied_role","ALTER ROLE ci_runtime SUPERUSER","SET LOCAL ROLE ci_admin"]
    for sql in denied:
        try:
            with engine.begin() as c: c.exec_driver_sql(sql)
        except DBAPIError as error:
            assert error.orig.sqlstate == "42501"
        else:
            raise AssertionError("EXPECTED_PERMISSION_DENIAL")
    engine.dispose()
    print(json.dumps({"api_check":"passed","manifest_match":True,"independent_login":True,"startup_without_ddl":True,"http_and_dml":True,"denied_operations":len(denied)}))
except Exception as error:
    print(json.dumps({"api_check":"failed","stage":stage,"error_type":type(error).__name__}))
    sys.exit(1)
'''


class RehearsalError(Exception):
    pass


class Docker:
    def run(self, args, *, data=None, timeout=20, check=True):
        try:
            result = subprocess.run(["docker", *args], input=data, text=True,
                                    capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as error:
            raise RehearsalError("DOCKER_COMMAND_UNCONFIRMED") from error
        if check and result.returncode:
            raise RehearsalError("DOCKER_COMMAND_FAILED")
        return result


class Rehearsal:
    def __init__(self, docker, api_image, pg_image, manifest, schema):
        # Validate before issuing any Docker command or creating resources.
        if not IMAGE.fullmatch(api_image) or not IMAGE.fullmatch(pg_image):
            raise RehearsalError("IMMUTABLE_IMAGE_IDS_REQUIRED")
        if not DIGEST.fullmatch(manifest):
            raise RehearsalError("INVALID_SOURCE_MANIFEST")
        self.docker, self.api_image, self.pg_image = docker, api_image, pg_image
        self.manifest, self.schema = manifest, schema
        self.token = secrets.token_hex(12)
        self.network = "market-role-net-" + self.token
        self.db = "market-role-db-" + self.token
        self.api = "market-role-api-" + self.token
        self.attempted = False

    def _image(self, image):
        result = self.docker.run(["image","inspect",image,"--format","{{json .Config}}"])
        return json.loads(result.stdout)

    def _container_id(self, name):
        result = self.docker.run(["ps","-aq","--no-trunc","--filter","name=^/"+name+"$"])
        ids = result.stdout.split()
        if len(ids) > 1:
            raise RehearsalError("AMBIGUOUS_TEST_CONTAINER")
        return ids[0] if ids else None

    def cleanup(self):
        """Only exact reserved names with this run's label; prove absence."""
        if not self.attempted:
            return True
        ok = True
        for name in (self.api, self.db):
            try:
                cid = self._container_id(name)
                if cid:
                    labels = json.loads(self.docker.run(["inspect","--type","container",cid,"--format","{{json .Config.Labels}}"] ).stdout) or {}
                    if labels.get(LABEL) != self.token:
                        raise RehearsalError("TEST_CONTAINER_OWNER_MISMATCH")
                    self.docker.run(["rm","-f","-v",cid])
                    if self._container_id(name):
                        raise RehearsalError("TEST_CONTAINER_REMOVAL_UNCONFIRMED")
            except (RehearsalError, ValueError, TypeError):
                ok = False
        try:
            ids = self.docker.run(["network","ls","--filter","name="+self.network,"--format","{{.ID}}"] ).stdout.split()
            if len(ids) > 1:
                raise RehearsalError("AMBIGUOUS_TEST_NETWORK")
            if ids:
                nid = ids[0]
                labels = json.loads(self.docker.run(["network","inspect",nid,"--format","{{json .Labels}}"] ).stdout) or {}
                members = json.loads(self.docker.run(["network","inspect",nid,"--format","{{json .Containers}}"] ).stdout) or {}
                if labels.get(LABEL) != self.token or members:
                    raise RehearsalError("TEST_NETWORK_REMOVAL_BLOCKED")
                self.docker.run(["network","rm",nid])
                if self.docker.run(["network","ls","--filter","name="+self.network,"--format","{{.ID}}"] ).stdout.strip():
                    raise RehearsalError("TEST_NETWORK_REMOVAL_UNCONFIRMED")
        except (RehearsalError, ValueError, TypeError):
            ok = False
        return ok

    def execute(self):
        # No deployed container inspection, env/config copying, pull or build.
        api_config, pg_config = self._image(self.api_image), self._image(self.pg_image)
        allowed_env = {"PATH","LANG","GPG_KEY","PYTHON_VERSION","PYTHON_SHA256",
                       "PYTHON_PIP_VERSION","PYTHON_SETUPTOOLS_VERSION","PYTHON_GET_PIP_URL",
                       "PYTHON_GET_PIP_SHA256","PYTHONDONTWRITEBYTECODE","PYTHONUNBUFFERED"}
        if any(item.partition("=")[0] not in allowed_env for item in (api_config.get("Env") or [])):
            raise RehearsalError("API_IMAGE_UNREVIEWED_ENVIRONMENT")
        if api_config.get("Volumes"):
            raise RehearsalError("API_IMAGE_IMPLICIT_VOLUMES_FORBIDDEN")
        if "PG_MAJOR=16" not in (pg_config.get("Env") or []):
            raise RehearsalError("POSTGRES_16_IMAGE_REQUIRED")
        if set(pg_config.get("Volumes") or {}) - {"/var/lib/postgresql/data"}:
            raise RehearsalError("POSTGRES_IMAGE_VOLUME_SCOPE_MISMATCH")
        with tempfile.TemporaryDirectory(prefix="market-role-") as folder:
            os.chmod(folder,0o700)
            admin_secret, runtime_secret = secrets.token_hex(32), secrets.token_hex(32)
            admin_env, runtime_env = Path(folder)/"pg.env", Path(folder)/"api.env"
            admin_env.write_text("POSTGRES_USER=ci_admin\nPOSTGRES_DB=test\nPOSTGRES_PASSWORD="+admin_secret+"\nPOSTGRES_HOST_AUTH_METHOD=scram-sha-256\nPGDATA=/var/lib/postgresql/data\n")
            runtime_env.write_text("DATABASE_URL=postgresql+psycopg://ci_runtime:"+runtime_secret+"@db:5432/test\nAPI_TOKEN="+secrets.token_hex(32)+"\nENABLE_SCHEDULER=false\nPGOPTIONS=-c statement_timeout=10000 -c lock_timeout=2000\nREHEARSAL_MANIFEST="+self.manifest+"\n")
            admin_env.chmod(0o600); runtime_env.chmod(0o600)
            self.attempted = True  # Reserve cleanup scope before any uncertain create.
            self.docker.run(["network","create","--internal","--label",LABEL+"="+self.token,self.network])
            self.docker.run(["run","-d","--pull=never","--name",self.db,"--label",LABEL+"="+self.token,
                "--network",self.network,"--network-alias","db","--env-file",str(admin_env),
                "--memory=512m","--cpus=1","--pids-limit=128","--security-opt=no-new-privileges",
                "--mount","type=tmpfs,destination=/var/lib/postgresql/data,tmpfs-size=268435456",self.pg_image])
            deadline = time.monotonic()+45
            while True:
                ready = self.docker.run(["exec",self.db,"pg_isready","-h","127.0.0.1","-U","ci_admin","-d","test"],check=False,timeout=5)
                if ready.returncode == 0: break
                if time.monotonic() >= deadline: raise RehearsalError("TEST_DATABASE_NOT_READY")
                time.sleep(0.5)
            grants = "\nCREATE ROLE ci_runtime LOGIN PASSWORD '"+runtime_secret+"' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;\nGRANT CONNECT ON DATABASE test TO ci_runtime;\nGRANT USAGE ON SCHEMA public TO ci_runtime;\n"
            for table, access in {"instruments":"SELECT,INSERT","daily_bars":"SELECT,INSERT,UPDATE","financial_snapshots":"SELECT,INSERT,UPDATE","paper_accounts":"SELECT,INSERT,UPDATE","paper_trades":"SELECT,INSERT"}.items():
                grants += f"GRANT {access} ON TABLE public.{table} TO ci_runtime;\nGRANT USAGE ON SEQUENCE public.{table}_id_seq TO ci_runtime;\n"
            setup = "BEGIN;\n"+self.schema+grants+"\nCOMMIT;\n"
            self.docker.run(["exec","-i",self.db,"psql","-X","-v","ON_ERROR_STOP=1","-U","ci_admin","-d","test"],data=setup)
            result = self.docker.run(["run","-i","--pull=never","--name",self.api,"--label",LABEL+"="+self.token,
                "--network",self.network,"--env-file",str(runtime_env),"--read-only","--user=10001:10001",
                "--cap-drop=ALL","--security-opt=no-new-privileges","--memory=512m","--cpus=1","--pids-limit=64",
                "--tmpfs","/tmp:rw,noexec,nosuid,size=33554432","--entrypoint","python",self.api_image,"-"],data=API_CHECK,timeout=120,check=False)
            try:
                report = json.loads(result.stdout.strip().splitlines()[-1])
            except (ValueError,IndexError,TypeError):
                raise RehearsalError("INVALID_API_TEST_REPORT") from None
            # Return only fixed status fields, never untrusted raw stdout/stderr.
            if result.returncode or report.get("api_check") != "passed":
                stage = report.get("stage")
                allowed = {"manifest","independent_login","startup_and_http","orm_dml","denied_operations"}
                raise RehearsalError("API_TEST_FAILED:"+(stage if stage in allowed else "unknown"))
            return {"isolated_api_acceptance":"passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image",required=True)
    parser.add_argument("--postgres-image",required=True)
    parser.add_argument("--expected-manifest",required=True)
    parser.add_argument("--schema-file",type=Path,required=True)
    parser.add_argument("--schema-sha256",required=True)
    args = parser.parse_args()
    rehearsal = None
    report = {"isolated_api_acceptance":"failed","production_modified":False}
    try:
        data = args.schema_file.read_bytes()
        if not DIGEST.fullmatch(args.schema_sha256) or hashlib.sha256(data).hexdigest()!=args.schema_sha256:
            raise RehearsalError("SCHEMA_CHECKSUM_MISMATCH")
        rehearsal = Rehearsal(Docker(),args.api_image,args.postgres_image,args.expected_manifest,data.decode())
        report = rehearsal.execute() | {"production_modified":False}
    except Exception as error:
        report["error"] = str(error) if isinstance(error,RehearsalError) else "INPUT_OR_REPORT_ERROR"
    finally:
        report["cleanup_confirmed"] = rehearsal.cleanup() if rehearsal else True
    if not report["cleanup_confirmed"]:
        report["isolated_api_acceptance"] = "blocked"
        report["test_resources_requiring_review"] = [rehearsal.api,rehearsal.db,rehearsal.network]
    print(json.dumps(report,sort_keys=True))
    return 0 if report["isolated_api_acceptance"]=="passed" and report["cleanup_confirmed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
