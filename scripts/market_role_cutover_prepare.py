#!/usr/bin/env python3
"""Prepare private API-only credential review files; never apply them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit, unquote

APP_KEYS = {"DATABASE_URL", "POSTGRES_PASSWORD", "API_TOKEN", "SEC_USER_AGENT",
            "IBKR_HOST", "IBKR_PORT", "IBKR_CLIENT_ID", "ENABLE_SCHEDULER"}
IMAGE_KEYS = {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256",
              "PYTHON_PIP_VERSION", "PYTHON_SETUPTOOLS_VERSION", "PYTHON_GET_PIP_URL",
              "PYTHON_GET_PIP_SHA256", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"}
GRANTS = {"instruments": "SELECT,INSERT", "daily_bars": "SELECT,INSERT,UPDATE",
          "financial_snapshots": "SELECT,INSERT,UPDATE",
          "paper_accounts": "SELECT,INSERT,UPDATE", "paper_trades": "SELECT,INSERT"}


class PreparationError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise PreparationError(code)


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, "READ_OR_CONFIG_CHECK_FAILED")
    return result.stdout


def environment(items):
    pairs = [item.split("=", 1) for item in (items or [])]
    require(all(len(pair) == 2 for pair in pairs), "INVALID_ENVIRONMENT")
    result = dict(pairs)
    require(len(result) == len(pairs), "DUPLICATE_ENVIRONMENT_KEY")
    return result


def decode_config(model):
    # Compose config escapes all dollars for reusable YAML/JSON output.
    for service in model["services"].values():
        service["environment"] = {
            k: v.replace("$$", "$") if isinstance(v, str) else v
            for k, v in service.get("environment", {}).items()
        }
    return model


def override_text(image, values):
    return ("services:\n  api:\n    image: " + json.dumps(image) + "\n"
            "    build: !reset null\n    pull_policy: never\n"
            "    env_file: !reset []\n    environment: !override " +
            json.dumps({k: v.replace("$", "$$") for k, v in values.items()}) + "\n")


def role_sql(role, password, database):
    require(role.startswith("market_runtime_") and role.replace("_", "").isalnum(),
            "INVALID_ROLE_NAME")
    require(password.isalnum(), "INVALID_GENERATED_PASSWORD")
    db_identifier = '"' + database.replace('"', '""') + '"'
    sql = ("-- REVIEW ONLY: not executed by the preparation utility.\n"
           "BEGIN;\nSET LOCAL lock_timeout='2s';\n"
           "SET LOCAL statement_timeout='10s';\n"
           f"CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB "
           "NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;\n"
           f"GRANT CONNECT ON DATABASE {db_identifier} TO {role};\n"
           f"GRANT USAGE ON SCHEMA public TO {role};\n")
    for table, access in GRANTS.items():
        sql += (f"GRANT {access} ON TABLE public.{table} TO {role};\n"
                f"GRANT USAGE ON SEQUENCE public.{table}_id_seq TO {role};\n")
    sql += ("DO $guard$ BEGIN\n"
            f"IF has_schema_privilege('{role}','public','CREATE') THEN\n"
            "RAISE EXCEPTION 'Runtime role inherits schema CREATE'; END IF;\n")
    for table, access in GRANTS.items():
        denied = "DELETE,TRUNCATE,REFERENCES,TRIGGER"
        if "UPDATE" not in access:
            denied += ",UPDATE"
        for privilege in denied.split(","):
            sql += (f"IF has_table_privilege('{role}','public.{table}','{privilege}') THEN\n"
                    "RAISE EXCEPTION 'Unexpected effective runtime privilege'; END IF;\n")
    return sql + "END; $guard$;\nCOMMIT;\n"


def private_write(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(text)


def prepare(api_name, base_path, output_parent):
    parent = Path(output_parent).resolve()
    mode = parent.stat()
    require(mode.st_uid == os.geteuid() and stat.S_IMODE(mode.st_mode) & 0o077 == 0,
            "OUTPUT_PARENT_MUST_BE_OWNER_PRIVATE")
    base = Path(base_path).resolve(strict=True)
    api = json.loads(command("docker", "inspect", api_name))[0]
    labels = api["Config"].get("Labels") or {}
    require(labels.get("com.docker.compose.service") == "api", "API_SERVICE_REQUIRED")
    require(labels.get("com.docker.compose.project.config_files") == str(base),
            "SINGLE_BASE_COMPOSE_REQUIRED")
    require(Path(labels.get("com.docker.compose.project.working_dir", "")).resolve()
            == base.parent, "COMPOSE_DIRECTORY_MISMATCH")
    require(api["State"]["Running"], "RUNNING_API_REQUIRED")
    project = labels["com.docker.compose.project"]
    image = api["Image"]
    require(image.startswith("sha256:") and len(image) == 71, "IMMUTABLE_IMAGE_REQUIRED")
    image_config = json.loads(command("docker", "image", "inspect", image))[0]["Config"]
    baked = environment(image_config.get("Env"))
    require(set(baked) <= IMAGE_KEYS and not image_config.get("Volumes"),
            "UNREVIEWED_IMAGE_DEFAULTS")
    compose = ["docker", "compose", "--project-directory", str(base.parent),
               "-p", project, "-f", str(base)]

    def config(*files):
        extra = [argument for file in files for argument in ("-f", str(file))]
        return decode_config(json.loads(command(*(compose + extra +
                                                  ["config", "--format", "json"]))))

    before = config()
    old = before["services"]["api"].get("environment", {})
    actual = environment(api["Config"].get("Env"))
    require(set(old) <= APP_KEYS and all(isinstance(v, str) for v in old.values()),
            "UNREVIEWED_APP_ENVIRONMENT")
    require(all(actual.get(k) == v for k, v in old.items()), "BASE_RUNTIME_ENV_DRIFT")
    require(set(actual) <= set(baked) | set(old) | {"HOME", "HOSTNAME"},
            "UNREVIEWED_RUNTIME_ENVIRONMENT")
    require(all(actual.get(k) == v for k, v in baked.items() if k not in old),
            "IMAGE_ENVIRONMENT_DRIFT")
    require(bool(old.get("API_TOKEN")), "API_TOKEN_REQUIRED")
    url = urlsplit(old["DATABASE_URL"])
    require(url.scheme in {"postgresql+psycopg", "postgresql"} and url.hostname
            and url.username and url.password and url.path.strip("/"), "POSTGRES_URL_REQUIRED")
    require(not url.query and not url.fragment, "REVIEW_CONNECTION_OPTIONS_FIRST")
    role = "market_runtime_" + secrets.token_hex(6)
    password = secrets.token_hex(32)
    new = {k: v for k, v in old.items() if k != "POSTGRES_PASSWORD"}
    new["DATABASE_URL"] = urlunsplit((url.scheme, role + ":" + password + "@" +
                                     url.netloc.rsplit("@", 1)[1], url.path, "", ""))
    require(before["services"]["api"].get("restart") ==
            api["HostConfig"]["RestartPolicy"]["Name"], "RESTART_POLICY_DRIFT")
    # Only the already reviewed local HTTP binding is accepted.
    expected_ports = {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}]}
    require(api["HostConfig"].get("PortBindings") == expected_ports, "PORT_REVIEW_REQUIRED")
    directory = Path(tempfile.mkdtemp(prefix="market-role-review-", dir=parent))
    try:
        runtime = directory / "runtime.compose.yml"
        rollback = directory / "rollback.compose.yml"
        private_write(runtime, override_text(image, new))
        private_write(rollback, override_text(image, old))
        changed = config(runtime)
        restored = config(runtime, rollback)
        expected = json.loads(json.dumps(before))
        expected_api = expected["services"]["api"]
        expected_api.pop("build", None)
        expected_api.update(image=image, pull_policy="never", environment=new)
        require(changed == expected, "RUNTIME_OVERRIDE_CHANGED_OTHER_CONFIGURATION")
        expected_api["environment"] = old
        require(restored == expected, "ROLLBACK_CONFIGURATION_MISMATCH")
        private_write(directory / "role.sql", role_sql(role, password, unquote(url.path[1:])))
        dependencies = {str(base), str(base.parent / ".env")}
        for service in before["services"].values():
            for item in service.get("env_file", []):
                dependencies.add(item if isinstance(item, str) else item["path"])
        source_hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                         for name in sorted(dependencies) if Path(name).is_file()}
        # Preserve service identities without writing their full secret-bearing configs.
        ids = command("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project).split()
        private_write(directory / "review.json", json.dumps({
            "project": project, "api_container_id": api["Id"], "api_image": image,
            "observed_project_container_ids": sorted(ids), "runtime_role": role,
            "source_file_sha256": source_hashes,
            "generated_file_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in (runtime, rollback, directory / "role.sql")},
            "production_modified": False, "applied": False,
        }, indent=2) + "\n")
        return {"review_directory": str(directory), "configuration_checks": "passed",
                "role_sql_executed": False, "services_restarted": False,
                "production_modified": False}
    except BaseException:
        shutil.rmtree(directory)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-container", required=True)
    parser.add_argument("--base-compose", required=True)
    parser.add_argument("--output-parent", required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.api_container, args.base_compose, args.output_parent)
    except Exception as error:
        # Never print subprocess output, environment values or connection URLs.
        result = {"preparation_failed": str(error) if isinstance(error, PreparationError)
                  else type(error).__name__, "production_modified": False}
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
