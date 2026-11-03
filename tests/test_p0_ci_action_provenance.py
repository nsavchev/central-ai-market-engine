"""Security regression for the repository's deliberately simple action-step style."""
import json
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
PINS = json.loads((ROOT / "release/ci-actions.lock.json").read_text())["actions"]


def check_actions(source):
    lines = source.splitlines()
    count = 0
    for index, line in enumerate(lines):
        match = re.match(r"^\s*-?\s*uses:\s*([^\s#]+)", line)
        if not match:
            continue
        count += 1
        name, separator, sha = match.group(1).partition("@")
        assert separator and name in PINS, "UNREVIEWED_ACTION"
        assert re.fullmatch(r"[a-f0-9]{40}", sha), "MUTABLE_ACTION_REFERENCE"
        assert sha == PINS[name]["sha"], "ACTION_PIN_DRIFT"
        if name == "actions/checkout":
            # All checked-in checkout steps use this explicit two-line mapping.
            assert index + 2 < len(lines), "CHECKOUT_CREDENTIALS_PERSISTED"
            assert lines[index + 1].strip() == "with:", "CHECKOUT_CREDENTIALS_PERSISTED"
            assert lines[index + 2].strip() == "persist-credentials: false", "CHECKOUT_CREDENTIALS_PERSISTED"
    assert count, "NO_ACTION_STEPS"


@pytest.mark.parametrize("path", sorted((ROOT / ".github/workflows").glob("*.yml")))
def test_workflow_action_provenance(path):
    check_actions(path.read_text())


@pytest.mark.parametrize("kind,error", [
    ("tag", "MUTABLE_ACTION_REFERENCE"),
    ("sha", "ACTION_PIN_DRIFT"),
    ("credentials", "CHECKOUT_CREDENTIALS_PERSISTED"),
])
def test_action_provenance_rejects_regressions(kind, error):
    sha = PINS["actions/checkout"]["sha"]
    source = "      - uses: actions/checkout@" + sha + "\n        with:\n          persist-credentials: false\n"
    if kind == "tag":
        source = source.replace(sha, "v4")
    elif kind == "sha":
        source = source.replace(sha, "0" * 40)
    else:
        source = source.replace("persist-credentials: false", "persist-credentials: true")
    with pytest.raises(AssertionError, match=error):
        check_actions(source)
