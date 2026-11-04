"""Opt-in restricted Docker execution of a candidate against operator-supplied tests.

Untrusted candidate *is executed*, but only in a disposable restricted container.
No claim of a hardened security boundary against kernel-level exploits.
"""
import ast
import math
import secrets
import hashlib
import os
import re
import subprocess
import stat
import tempfile
import shutil
import uuid
from pathlib import Path


def _read_input(path):
    """Read bounded regular-file bytes through one no-follow descriptor."""
    if not path.is_absolute() or path.suffix != ".py":
        raise ValueError("UNSAFE_INPUT")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            metadata = os.fstat(source.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 32768
                    or metadata.st_mode & 0o022 or metadata.st_nlink != 1):
                raise ValueError("UNSAFE_INPUT")
            data = source.read(32769)
            if len(data) > 32768:
                raise ValueError("UNSAFE_INPUT")
            return data
    except OSError as error:
        raise ValueError("UNSAFE_INPUT") from error


# This deliberately supports only the first reviewed arithmetic scenario. It is
# not a sandbox for arbitrary Python; unsupported candidates never reach Docker.
EXECUTION_POLICY = 'bounded-arithmetic-v1'


def _validate_bounded_candidate(data):
    def reject():
        raise ValueError('CANDIDATE_OUTSIDE_EXECUTION_POLICY')
    try:
        tree = ast.parse(data)
    except (SyntaxError, ValueError, RecursionError):
        reject()
    if not 1 <= len(tree.body) <= 8 or sum(1 for _ in ast.walk(tree)) > 256:
        reject()
    identifiers = set()
    def expression(node, parameters, depth=0):
        if depth > 16:
            reject()
        if isinstance(node, ast.Constant):
            if type(node.value) not in (int, float) or abs(node.value) > 1_000_000 or not math.isfinite(node.value):
                reject()
        elif isinstance(node, ast.Name) and node.id in parameters and isinstance(node.ctx, ast.Load):
            pass
        elif isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod):
            expression(node.left, parameters, depth+1)
            expression(node.right, parameters, depth+1)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            expression(node.operand, parameters, depth+1)
        else:
            reject()
    def identifier(name):
        return isinstance(name, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name) and '__' not in name
    for function in tree.body:
        if (not isinstance(function, ast.FunctionDef) or not identifier(function.name)
                or function.name in identifiers or function.decorator_list or function.returns
                or getattr(function, 'type_params', []) or function.type_comment
                or len(function.body) != 1 or not isinstance(function.body[0], ast.Return)):
            reject()
        identifiers.add(function.name)
        args = function.args
        parameters = args.posonlyargs + args.args
        if (args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.kw_defaults
                or len(parameters) > 8 or any(not identifier(arg.arg) or arg.annotation or arg.type_comment for arg in parameters)
                or len({arg.arg for arg in parameters}) != len(parameters)):
            reject()
        expression(function.body[0].value, {arg.arg for arg in parameters})


def _confirm_container_absent(run, container_name):
    """Require a successful exact-name daemon query, including after removal."""
    def probe():
        result = run(
            ['docker', 'container', 'ls', '--all', '--filter', 'name=^/' + container_name + '$',
             '--format', '{{.Names}}'],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0 or not isinstance(result.stdout, str):
            return None
        names = result.stdout.splitlines()
        if not names:
            return True
        return False if names == [container_name] else None
    try:
        absent = probe()
        if absent is not False:
            return absent is True
        removed = run(['docker', 'rm', '-f', container_name],
                      capture_output=True, text=True, timeout=10, check=False)
        return removed.returncode == 0 and probe() is True
    except (subprocess.TimeoutExpired, OSError):
        return False


def run_functional_tests(*, enabled, candidate, expected_sha256, test_file, image,
                         expected_test_sha256=None, timeout=30, run=subprocess.run,
                         record_resources=None):
    if enabled != "YES":
        raise ValueError("FUNCTIONAL_TESTS_DISABLED")
    paths = [Path(candidate), Path(test_file)]
    contents = [_read_input(path) for path in paths]
    if paths[0].resolve() == paths[1].resolve():
        raise ValueError("TEST_FILE_MUST_BE_SEPARATE")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("INVALID_HASH")
    if hashlib.sha256(contents[0]).hexdigest() != expected_sha256:
        raise ValueError("CANDIDATE_HASH_MISMATCH")
    if not isinstance(expected_test_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_test_sha256):
        raise ValueError("INVALID_TEST_HASH")
    if hashlib.sha256(contents[1]).hexdigest() != expected_test_sha256:
        raise ValueError("TEST_HASH_MISMATCH")
    if not isinstance(image, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}", image
    ):
        raise ValueError("UNPINNED_IMAGE")
    if type(timeout) is not int or not 5 <= timeout <= 60:
        raise ValueError("INVALID_TIMEOUT")
    if record_resources is not None and not callable(record_resources):
        raise ValueError("INVALID_RESOURCE_RECORDER")
    _validate_bounded_candidate(contents[0])
    # Never bind caller-owned paths after checking their hashes.
    # The dedicated runner account/host is trusted; this is not host-root isolation.
    snapshot_root = Path(tempfile.mkdtemp(prefix="central-ai-input-"))
    cleanup_confirmed = True
    try:
        snapshot_paths = [snapshot_root / "candidate.py", snapshot_root / "test_candidate.py"]
        for path, data in zip(snapshot_paths, contents):
            path.write_bytes(data)
            path.chmod(0o444)
        completion_record = ('CENTRAL_AI_COMPLETED_V1:' + secrets.token_hex(32) + ':'
                             + expected_sha256 + ':' + expected_test_sha256)
        harness = snapshot_root / 'harness.py'
        # Candidate policy excludes imports/calls/attributes and all executable
        # module statements except undecorated arithmetic function definitions.
        # Operator-supplied tests and the Python/image/host remain trusted.
        harness.write_text("import os\nimport runpy\n"
                           "runpy.run_path('/sandbox/test_candidate.py', run_name='__main__')\n"
                           + "os.write(1, " + repr(('\n' + completion_record + '\n').encode()) + ")\n")
        harness.chmod(0o444)
        container_name = 'central-ai-verifier-' + uuid.uuid4().hex
        cmd = [
            'docker', 'run', '--name', container_name, '--rm', '--pull=never',
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit=32",
            "--memory=128m", "--cpus=0.5", "--user=65534:65534",
            "--mount", "type=bind,src=" + str(snapshot_paths[0]) + ",dst=/sandbox/candidate.py,readonly",
            "--mount", "type=bind,src=" + str(snapshot_paths[1]) + ",dst=/sandbox/test_candidate.py,readonly",
            "--mount", "type=bind,src=" + str(harness) + ",dst=/sandbox/harness.py,readonly",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=8m",
            "--workdir", "/tmp", "--entrypoint", "python",
            image, "-I", "-B", "/sandbox/harness.py",
        ]
        resources = {"snapshot_directory": str(snapshot_root), "container_name": container_name}
        # A durable journal callback must return before Docker can see a command.
        if record_resources is not None:
            record_resources(dict(resources))
        cleanup_confirmed = False
        try:
            result = run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
            lines = result.stdout.splitlines() if isinstance(getattr(result, "stdout", None), str) else []
            completed = (result.returncode == 0 and bool(lines)
                         and lines[-1] == completion_record and lines.count(completion_record) == 1)
            report = {"test_sha256": expected_test_sha256,
                      "status": ("passed" if completed else "completion_unconfirmed") if result.returncode == 0 else "failed",
                      "passed": completed, "executed_candidate": True,
                      "completion_confirmed": completed, "execution_policy": EXECUTION_POLICY,
                      "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            report = {"status": "timeout", "passed": False, "executed_candidate": True}
        except OSError:
            report = {"status": "execution_error", "passed": False, "executed_candidate": True}
        finally:
            # Neither client exit nor a successful rm proves daemon-side absence.
            # Also run on cancellation; an interrupted/failed probe keeps inputs.
            cleanup_confirmed = _confirm_container_absent(run, container_name)
        if not cleanup_confirmed:
            return dict(resources, status="cleanup_unconfirmed", passed=False, executed_candidate=True,
                        execution_policy=EXECUTION_POLICY, completion_confirmed=False)
        return dict(report, execution_policy=EXECUTION_POLICY,
                    completion_confirmed=report.get("completion_confirmed", False))

    finally:
        # Preserve inputs on cleanup uncertainty for operator quarantine/inspection.
        if cleanup_confirmed:
            shutil.rmtree(snapshot_root)
