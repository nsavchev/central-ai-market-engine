#!/usr/bin/env python3
"""Opt-in, source-only architecture inventory. No imports of application modules."""
import ast
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/opt/central-ai/release-v1/market_engine_v0_9")
REPO = Path("/opt/central-ai/github-export")
AREAS = ("app", "central_ai", "developer_agent")
LIMIT = 1_000_000

def inventory(root=ROOT, repo=REPO):
    modules, definitions, edges, problems = {}, defaultdict(list), [], []
    for area in AREAS:
        directory = root / area
        if not directory.is_dir() or directory.is_symlink():
            problems.append("missing_area:" + area)
            continue
        for path in sorted(directory.rglob("*.py")):
            if any(part.startswith(".") or part in ("__pycache__", "workspaces") for part in path.relative_to(directory).parts):
                continue
            if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT:
                problems.append("unreadable_or_large:" + path.relative_to(root).as_posix())
                continue
            key = path.relative_to(root).as_posix()
            try:
                data = path.read_bytes()
                tree = ast.parse(data, filename=key)
            except (OSError, SyntaxError, UnicodeError, ValueError):
                problems.append("parse_failed:" + key)
                continue
            peer = repo / key
            peer_hash = hashlib.sha256(peer.read_bytes()).hexdigest() if peer.is_file() and not peer.is_symlink() and peer.stat().st_size <= LIMIT else None
            digest = hashlib.sha256(data).hexdigest()
            modules[key] = {"sha256": digest, "git_export_match": peer_hash == digest if peer_hash else None}
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    definitions[node.name].append(key)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(AREAS):
                            edges.append([key, alias.name])
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith(AREAS):
                        edges.append([key, node.module])
    return {
        "schema": "architecture-source-inventory-v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "module_count": len(modules),
        "modules": modules,
        "local_imports": sorted(edges),
        "same_name_candidates": {name: sorted(paths) for name, paths in sorted(definitions.items()) if len(paths) > 1},
        "issues": sorted(problems),
        "note": "Duplicate names do not prove duplicate behavior. Source files are not proof of loaded container images.",
        "audit_complete": False, "deployment_authorized": False,
    }

if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2, sort_keys=True))
