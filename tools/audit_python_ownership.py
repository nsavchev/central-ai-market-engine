"""Read-only AST inventory of project Python definitions and local imports.

No imports/execution of target modules, network, file writes or code mutation.
"""
import argparse
import ast
import json
from collections import defaultdict
from pathlib import Path

ROOTS = ("app", "central_ai", "developer_agent")
SKIP = {"__pycache__", ".venv", "venv"}

def inventory(root: Path):
    root = root.resolve()
    definitions, references, failures = [], [], []
    for dirname in ROOTS:
        base = root / dirname
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if SKIP.intersection(path.relative_to(root).parts):
                continue
            rel = path.relative_to(root).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except (SyntaxError, UnicodeError) as exc:
                failures.append({"path": rel, "reason": type(exc).__name__})
                continue
            module = rel[:-3].replace("/", ".")
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    definitions.append({"path": rel, "name": node.name, "line": node.lineno,
                                        "kind": type(node).__name__})
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(ROOTS):
                            references.append({"from": module, "to": alias.name, "line": node.lineno})
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module and node.module.startswith(ROOTS):
                        references.append({"from": module, "to": node.module, "line": node.lineno})
                    elif node.level and node.module:
                        components = module.split(".")[:-node.level]
                        target = ".".join(components + node.module.split("."))
                        references.append({"from": module, "to": target, "line": node.lineno})
    by_name = defaultdict(list)
    for row in definitions:
        by_name[row["name"]].append(row["path"])
    repeated = {k: sorted(set(v)) for k,v in sorted(by_name.items())
                if len(set(v)) > 1 and not k.startswith("_")}
    return {"definitions": definitions, "imports": references,
            "same_named_definitions": repeated, "parse_failures": failures}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    print(json.dumps(inventory(Path(args.root)), sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
