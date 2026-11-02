"""Read-only preflight of AI candidate release safety; never deploy."""
from pathlib import Path
import json

def inspect_release(*, enabled, release_root):
    if enabled != "YES":
        raise ValueError("PREFLIGHT_DISABLED")
    root = Path(release_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("INVALID_RELEASE_ROOT")
    compose = root / "docker-compose.central.release.yml"
    if compose.is_symlink() or not compose.is_file():
        raise ValueError("RELEASE_CONFIG_MISSING")
    text = compose.read_text("utf-8")
    # This preflight is conservative, not a substitute for docker compose config.
    required = ["CENTRAL_TASK_API_ENABLED:", "NO", "CENTRAL_TASK_DB:",
                "central_ai_tasks:", "external: true",
                "market_engine_v0_9_central_ai_tasks"]
    if not all(part in text for part in required):
        raise ValueError("RELEASE_GATES_MISSING")
    return {"status":"config_present","executed":False,
            "deployed":False,"production_modified":False}
