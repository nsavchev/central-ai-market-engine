"""P0: release build must be explicitly pinned; never trust floating tags."""
from pathlib import Path
import re


def validate_release_dockerfile(path):
    source = Path(path).read_text("utf-8")
    from_lines = [line.strip() for line in source.splitlines()
                  if line.strip().upper().startswith("FROM ")]
    if len(from_lines) != 1 or not re.fullmatch(
        r"FROM python:3\.12(?:\.\d+)?-slim(?:-[a-z0-9]+)?@sha256:[0-9a-f]{64}",
        from_lines[0], re.I):
        raise ValueError("UNPINNED_BASE_IMAGE")
    if "pip install --no-cache-dir" in source and "--require-hashes" not in source:
        raise ValueError("UNLOCKED_DEPENDENCIES")
    if not re.search(r"(?m)^USER 10001\s*$", source):
        raise ValueError("NONROOT_REQUIRED")
    return True
