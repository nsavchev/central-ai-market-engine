import ast
from pathlib import Path
from tools.audit_python_ownership import inventory

def test_inventory_detects_imports_and_duplicates(tmp_path):
    a=tmp_path/"central_ai"
    b=tmp_path/"developer_agent"
    a.mkdir()
    b.mkdir()
    (a/"one.py").write_text("from developer_agent.two import Worker\ndef process(): pass\n")
    (b/"two.py").write_text("class Worker: pass\ndef process(): pass\n")
    result=inventory(tmp_path)
    assert len(result["definitions"])==3
    assert result["same_named_definitions"]["process"]==["central_ai/one.py","developer_agent/two.py"]
    assert result["imports"]==[{"from":"central_ai.one","to":"developer_agent.two","line":1}]
    assert result["parse_failures"]==[]

def test_inventory_never_executes_target_code(tmp_path):
    a=tmp_path/"app"
    a.mkdir()
    (a/"unsafe.py").write_text("raise RuntimeError('MUST_NOT_EXECUTE')\ndef harmless(): pass\n")
    assert inventory(tmp_path)["definitions"][0]["name"]=="harmless"
