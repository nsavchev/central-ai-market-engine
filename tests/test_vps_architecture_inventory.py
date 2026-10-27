import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("inventory", Path(__file__).resolve().parents[1] / "tools/vps_architecture_inventory.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_inventory_no_import_or_execution(tmp_path):
    release, repo = tmp_path / "release", tmp_path / "repo"
    (release / "central_ai").mkdir(parents=True)
    (repo / "central_ai").mkdir(parents=True)
    source = "raise RuntimeError('must never execute')\nimport central_ai.app\ndef shared(): pass\n"
    (release / "central_ai/a.py").write_text(source)
    (repo / "central_ai/a.py").write_text(source)
    (release / "central_ai/b.py").write_text("def shared(): pass\n")
    result = mod.inventory(release, repo)
    assert result["module_count"] == 2
    assert result["modules"]["central_ai/a.py"]["git_export_match"] is True
    assert result["same_name_candidates"]["shared"] == ["central_ai/a.py", "central_ai/b.py"]
    assert result["local_imports"] == [["central_ai/a.py", "central_ai.app"]]
    assert result["audit_complete"] is False
    assert result["deployment_authorized"] is False

def test_bad_source_is_reported(tmp_path):
    release, repo = tmp_path / "release", tmp_path / "repo"
    (release / "app").mkdir(parents=True)
    repo.mkdir()
    (release / "app/bad.py").write_text("def broken(\n")
    result = mod.inventory(release, repo)
    assert "parse_failed:app/bad.py" in result["issues"]
