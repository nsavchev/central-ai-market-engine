"""A11.15.7 disposable repair rehearsal and rollback.

Operates ONLY on a temporary isolated copy; never applies to source workspace.
"""
import hashlib
from pathlib import Path
import shutil
import tempfile

from central_ai.isolated_repair_stager import IsolatedRepairStager, _safe_relative


class RepairRollbackRehearsal:
    def __init__(self, workspace, staging_root):
        self.stager = IsolatedRepairStager(workspace, staging_root)

    def rehearse(self, filename, expected_sha256, replacement):
        relative = _safe_relative(filename)
        source = self.stager.workspace / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError("UNSAFE_TARGET")
        source_bytes = source.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != expected_sha256:
            raise ValueError("SOURCE_CHANGED")
        verified = self.stager.stage(filename, expected_sha256, replacement)
        with tempfile.TemporaryDirectory(
            prefix="rollback-rehearsal-", dir=self.stager.staging_root
        ) as temporary:
            copy = Path(temporary) / "candidate.py"
            backup = Path(temporary) / "original.bak"
            backup.write_bytes(source_bytes)
            copy.write_bytes(source_bytes)
            copy.write_bytes(replacement.encode("utf-8"))
            if hashlib.sha256(copy.read_bytes()).hexdigest() != verified["candidate_sha256"]:
                raise RuntimeError("CANDIDATE_HASH_MISMATCH")
            shutil.copyfile(backup, copy)
            restored = hashlib.sha256(copy.read_bytes()).hexdigest()
            if restored != expected_sha256:
                raise RuntimeError("ROLLBACK_VERIFICATION_FAILED")
        # Fail closed if trusted workspace was modified concurrently.
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha256:
            raise RuntimeError("SOURCE_CHANGED_DURING_REHEARSAL")
        return {
            "filename": str(relative),
            "candidate_sha256": verified["candidate_sha256"],
            "original_sha256": expected_sha256,
            "rollback_rehearsed": True,
            "applied": False,
            "deployment_allowed": False,
        }
