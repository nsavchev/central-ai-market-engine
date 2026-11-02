"""P0 static check of an isolated pinned image recipe and pip-tools lock.

Not a registry authenticity check or guarantee of byte-identical Docker images.
"""
from pathlib import Path
import re

_PACKAGE = re.compile(r"^[A-Za-z0-9_.-]+==[A-Za-z0-9][A-Za-z0-9_.+!-]*$")
_HASH = re.compile(r"^--hash=sha256:[a-f0-9]{64}$")


def validate_release_dockerfile(path):
    path = Path(path)
    source = path.read_text("utf-8")
    from_lines = [x.strip() for x in source.splitlines()
                  if x.strip().upper().startswith("FROM ")]
    if len(from_lines) != 1 or not re.fullmatch(
        r"FROM python(?:[:][a-zA-Z0-9._-]+)?@sha256:[0-9a-f]{64}",
        from_lines[0]):
        raise ValueError("UNPINNED_BASE_IMAGE")
    copied = re.findall(r"(?m)^COPY (\S*requirements\.lock) /srv/requirements\.lock\s*$", source)
    if len(copied) != 1:
        raise ValueError("LOCKFILE_NOT_COPIED")
    if not re.search(
        r"(?m)^RUN pip install --no-cache-dir --require-hashes -r /srv/requirements\.lock\s*$",
        source):
        raise ValueError("UNLOCKED_DEPENDENCIES")
    # Docker COPY is resolved against the repository build context, not Dockerfile.parent.
    lock = path.parent.parent / copied[0] if path.parent.name == "release-evidence" else path.parent / copied[0]
    if not lock.is_file() or lock.is_symlink():
        raise ValueError("LOCKFILE_MISSING")
    # pip-compile generated files use backslash continuations and comments.
    # Reject any non-comment logical line not composed of an exact pin and hashes.
    logical = []
    buf = ""
    for raw in lock.read_text("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            buf += line[:-1].strip() + " "
            continue
        buf += line
        if buf.startswith("--"):
            raise ValueError("UNPINNED_LOCK_ENTRY")
        logical.append(buf.split(" #", 1)[0].strip())
        buf = ""
    if buf or not logical:
        raise ValueError("INVALID_LOCKFILE")
    names = set()
    for line in logical:
        parts = line.split()
        if len(parts) < 2 or not _PACKAGE.fullmatch(parts[0]) or not all(_HASH.fullmatch(x) for x in parts[1:]):
            raise ValueError("UNPINNED_LOCK_ENTRY")
        name = parts[0].split("==", 1)[0].lower().replace("_", "-")
        if name in names:
            raise ValueError("DUPLICATE_LOCK_ENTRY")
        names.add(name)
    if not re.search(r"(?m)^USER 10001\s*$", source):
        raise ValueError("NONROOT_REQUIRED")
    return True
