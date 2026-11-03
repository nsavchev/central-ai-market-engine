from pathlib import Path
import pytest
from central_ai.release_build_policy import validate_release_dockerfile


def test_unpinned_production_dockerfile_is_rejected():
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="UNPINNED_BASE_IMAGE"):
        validate_release_dockerfile(root / "central_ai" / "Dockerfile")


def test_release_dockerfile_policy(tmp_path):
    path = tmp_path / "Dockerfile"
    text = (
        "FROM python:3.12.8-slim-bookworm@sha256:" + "a" * 64 +
        "\nWORKDIR /srv\nCOPY requirements.lock /srv/requirements.lock\n"
        "RUN pip install --no-cache-dir --require-hashes -r /srv/requirements.lock\n"
        "USER 10001\n"
    )
    path.write_text(text)
    lock = tmp_path / "requirements.lock"
    lock.write_text("fastapi==0.115.6 --hash=sha256:" + "b" * 64 + "\n")
    assert validate_release_dockerfile(path)
    lock.write_text("fastapi>=0.115\n")
    with pytest.raises(ValueError, match="UNPINNED_LOCK_ENTRY"):
        validate_release_dockerfile(path)
    lock.write_text("fastapi==0.115.6 --hash=sha256:" + "b" * 64 + "\n")
    path.write_text(text.replace("--require-hashes ", ""))
    with pytest.raises(ValueError, match="UNLOCKED_DEPENDENCIES"):
        validate_release_dockerfile(path)
    path.write_text(text.replace("COPY requirements.lock /srv/requirements.lock\n", ""))
    with pytest.raises(ValueError, match="LOCKFILE_NOT_COPIED"):
        validate_release_dockerfile(path)


def test_compact_linux_lock_in_release_context(tmp_path):
    directory = tmp_path / "release-evidence"
    directory.mkdir()
    path = directory / "Dockerfile.release"
    path.write_text(
        "FROM python@sha256:" + "a" * 64 + "\n"
        "COPY release-evidence/requirements-linux-amd64.lock /srv/requirements.lock\n"
        "RUN pip install --no-cache-dir --require-hashes -r /srv/requirements.lock\n"
        "USER 10001\n"
    )
    lock = directory / "requirements-linux-amd64.lock"
    lock.write_text("fastapi==0.162.0 --hash=sha256:" + "b" * 64 + "\n")
    assert validate_release_dockerfile(path)
    lock.write_text("fastapi==0.162.0\n")
    with pytest.raises(ValueError, match="UNPINNED_LOCK_ENTRY"):
        validate_release_dockerfile(path)
