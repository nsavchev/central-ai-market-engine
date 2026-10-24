"""A11.15.7: isolated, bounded patch staging without code execution.

Never modifies the original workspace. Caller must explicitly review the
staged artifact before any separate application process.
"""
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import tempfile


def _safe_relative(filename):
    if not isinstance(filename, str) or not filename:
        raise ValueError("INVALID_FILENAME")
    path = PurePosixPath(filename)
    if (path.is_absolute() or path.suffix != ".py"
            or "\\" in filename or
            any(part in ("", ".", "..") for part in filename.split("/"))):
        raise ValueError("PATH_BLOCKED")
    return path


class IsolatedRepairStager:
    """Stage one Python source candidate outside the trusted workspace."""

    def __init__(self, workspace, staging_root):
        self.workspace = Path(workspace).resolve(strict=True)
        self.staging_root = Path(staging_root).resolve(strict=True)
        if not self.workspace.is_dir() or not self.staging_root.is_dir():
            raise ValueError("INVALID_DIRECTORY")
        if (self.staging_root == self.workspace
                or self.staging_root.is_relative_to(self.workspace)
                or self.workspace.is_relative_to(self.staging_root)):
            raise ValueError("STAGING_NOT_ISOLATED")

    def stage(self, filename, expected_sha256, replacement):
        relative = _safe_relative(filename)
        if not isinstance(expected_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_sha256
        ):
            raise ValueError("INVALID_EXPECTED_HASH")
        if not isinstance(replacement, str):
            raise ValueError("INVALID_REPLACEMENT")
        replacement_bytes = replacement.encode("utf-8")
        if len(replacement_bytes) > 1024 * 1024:
            raise ValueError("REPLACEMENT_TOO_LARGE")
        target = self.workspace / relative
        if target.is_symlink() or not target.is_file():
            raise ValueError("UNSAFE_TARGET")
        resolved = target.resolve(strict=True)
        if not resolved.is_relative_to(self.workspace):
            raise ValueError("PATH_BLOCKED")
        original = resolved.read_bytes()
        actual = hashlib.sha256(original).hexdigest()
        if actual != expected_sha256:
            raise ValueError("SOURCE_CHANGED")
        compile(replacement, str(relative), "exec")  # syntax only; no execution
        candidate_hash = hashlib.sha256(replacement_bytes).hexdigest()
        with tempfile.TemporaryDirectory(
            prefix="repair-", dir=self.staging_root
        ) as temporary:
            staging_dir = Path(temporary)
            candidate = staging_dir / "candidate.py"
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(replacement_bytes)
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != candidate_hash:
                raise RuntimeError("STAGING_VERIFICATION_FAILED")
            # The temporary candidate is intentionally deleted after verification.
            # No executable or patch is applied to the trusted workspace.
            return {
                "filename": str(relative),
                "original_sha256": actual,
                "candidate_sha256": candidate_hash,
                "syntax_valid": True,
                "applied": False,
                "rollback_required": False,
            }
