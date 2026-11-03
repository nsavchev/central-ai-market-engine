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



def test_source_controlled_release_recipe_and_no_compile_gate(tmp_path):
    root = Path(__file__).resolve().parents[1]
    assert validate_release_dockerfile(root / "release" / "Dockerfile.release")
    recipe = (root / "release" / "Dockerfile.release").read_text()
    assert "ENV PYTHONDONTWRITEBYTECODE=1" in recipe
    assert "RUN pip install --no-cache-dir --no-compile --require-hashes -r /srv/requirements.lock" in recipe
    directory = tmp_path / "release"
    directory.mkdir()
    lock = directory / "requirements-linux-amd64.lock"
    lock.write_text("fastapi==0.162.0 --hash=sha256:" + "b" * 64 + "\n")
    path = directory / "Dockerfile.release"
    path.write_text(recipe)
    assert validate_release_dockerfile(path)
    path.write_text(recipe.replace("--require-hashes ", ""))
    with pytest.raises(ValueError, match="UNLOCKED_DEPENDENCIES"):
        validate_release_dockerfile(path)
    path.write_text(recipe)
    lock.write_text("fastapi==0.162.0\n")
    with pytest.raises(ValueError, match="UNPINNED_LOCK_ENTRY"):
        validate_release_dockerfile(path)



@pytest.mark.parametrize("drift,expected", [
    ("none", None),
    ("id", "IMAGE_ID_DRIFT"),
    ("layers", "ROOTFS_LAYER_DRIFT"),
    ("files", "FILESYSTEM_DRIFT"),
    ("config", "RUNTIME_CONFIG_DRIFT"),
    ("root", "NONROOT_REQUIRED"),
])
def test_image_comparison_fails_closed(tmp_path, monkeypatch, drift, expected):
    import copy
    import json
    import textwrap
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/p0-locked-image-candidate.yml").read_text()
    script = textwrap.dedent(workflow.split("          python - <<'PY'\n", 1)[1].split("          PY\n", 1)[0])
    monkeypatch.chdir(tmp_path)
    evidence = tmp_path / "release-evidence"
    evidence.mkdir()
    a = {"Id": "sha256:a", "Config": {"User": "10001"}, "RootFS": {"Layers": ["a"]}, "Created": "fixed"}
    b = copy.deepcopy(a)
    if drift == "id":
        b["Id"] = "sha256:b"
    elif drift == "layers":
        b["RootFS"]["Layers"] = ["b"]
    elif drift == "config":
        b["Config"]["Cmd"] = ["unexpected"]
    elif drift == "root":
        a["Config"]["User"] = b["Config"]["User"] = "0"
    for label, image in (("candidate", a), ("rebuilt", b)):
        (evidence / (label + "-inspect.json")).write_text(json.dumps([image]))
        row = {"path": "/srv/example", "sha256": "content", "mtime_ns": 1}
        if drift == "files" and label == "rebuilt":
            row["mtime_ns"] = 2
        (evidence / (label + "-files.jsonl")).write_text(json.dumps(row) + "\n")
    if expected:
        with pytest.raises(AssertionError, match=expected):
            exec(compile(script, "<workflow-comparison>", "exec"), {})
    else:
        exec(compile(script, "<workflow-comparison>", "exec"), {})
    report = json.loads((evidence / "image-comparison.json").read_text())
    assert report["deployment_authorized"] is False
