from pathlib import Path
import pytest
from central_ai.release_build_policy import validate_release_dockerfile


def test_unpinned_production_dockerfile_is_rejected():
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="UNPINNED_BASE_IMAGE"):
        validate_release_dockerfile(root / "central_ai" / "Dockerfile")


def test_release_dockerfile_policy(tmp_path):
    path = tmp_path / "Dockerfile"
    path.write_text(
        "FROM python:3.12.8-slim-bookworm@sha256:" + "a" * 64 +
        "\nRUN pip install --no-cache-dir --require-hashes -r requirements.lock\n"
        "USER 10001\n")
    assert validate_release_dockerfile(path)
    path.write_text(path.read_text().replace("--require-hashes", ""))
    with pytest.raises(ValueError, match="UNLOCKED_DEPENDENCIES"):
        validate_release_dockerfile(path)
