"""P0 static release gate. Does not validate registry digest authenticity."""
from pathlib import Path
import re


def validate_release_dockerfile(path):
    path = Path(path)
    source = path.read_text("utf-8")
    from_lines = [line.strip() for line in source.splitlines()
                  if line.strip().upper().startswith("FROM ")]
    if len(from_lines) != 1 or not re.fullmatch(
        r"FROM python:3\.12(?:\.\d+)?-slim(?:-[a-z0-9]+)?@sha256:[0-9a-f]{64}",
        from_lines[0], re.I):
        raise ValueError("UNPINNED_BASE_IMAGE")
    if not re.search(r"(?m)^COPY requirements\.lock /srv/requirements\.lock\s*$", source):
        raise ValueError("LOCKFILE_NOT_COPIED")
    if not re.search(
        r"(?m)^RUN pip install --no-cache-dir --require-hashes -r /srv/requirements\.lock\s*$",
        source):
        raise ValueError("UNLOCKED_DEPENDENCIES")
    lock = path.parent / "requirements.lock"
    if not lock.is_file() or lock.is_symlink():
        raise ValueError("LOCKFILE_MISSING")
    entries = [x.strip() for x in lock.read_text("utf-8").splitlines()
               if x.strip() and not x.lstrip().startswith("#")]
    if not entries:
        raise ValueError("LOCKFILE_EMPTY")
    for line in entries:
        if not re.fullmatch(
            r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+\s+--hash=sha256:[0-9a-f]{64}(?:\s+--hash=sha256:[0-9a-f]{64})*",
            line):
            raise ValueError("UNPINNED_LOCK_ENTRY")
    if not re.search(r"(?m)^USER 10001\s*$", source):
        raise ValueError("NONROOT_REQUIRED")
    return True
