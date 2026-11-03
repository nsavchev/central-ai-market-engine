"""AI-13: validate a draft proposal before manual verifier handoff.

This module never executes source, runs tests, writes to workspaces or deploys.
"""
import json
import hmac
import re
import time
from pathlib import Path


def check_proposal_for_verifier(*, enabled, proposal_path):
    if enabled != "YES":
        raise ValueError("VERIFIER_GATE_DISABLED")
    path = Path(proposal_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("INVALID_PROPOSAL")
    if path.stat().st_size > 65536 or path.stat().st_mode & 0o022:
        raise ValueError("UNSAFE_PROPOSAL")
    data = json.loads(path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("INVALID_PROPOSAL")
    if (
        data.get("status") != "draft"
        or data.get("approved") is not False
        or data.get("deployment_allowed") is not False
        or data.get("production_modified") is not False
        or data.get("patch") is not None
        or data.get("target") is not None
        or data.get("test_status") != "not_run"
        or data.get("review_status") != "pending"
        or data.get("tests") != []
    ):
        raise ValueError("VERIFIER_GATE_BLOCKED")
    suggestions = data.get("ai_recommendations")
    if (
        not isinstance(suggestions, list)
        or len(suggestions) != 1
        or not isinstance(suggestions[0], str)
        or not suggestions[0].strip()
    ):
        raise ValueError("INVALID_RECOMMENDATIONS")
    return {
        "proposal_id": data.get("id"),
        "verifier_status": "awaiting_isolated_candidate",
        "tests_executed": False,
        "approved": False,
        "deployment_allowed": False,
    }



def make_hmac_review_authorizer(*, reviewer_keys, request_receipt, clock=time.time):
    """Build a verify-only adapter from trusted host configuration.

    Shared-key authentication proves possession of a configured reviewer key,
    not a human identity or a non-repudiable digital signature. Never expose
    keys or dependency injection to candidates/HTTP request parameters.
    """
    if (not isinstance(reviewer_keys, dict) or not reviewer_keys
            or not callable(request_receipt) or not callable(clock)):
        raise ValueError("REVIEW_AUTHORIZER_NOT_CONFIGURED")
    keys = dict(reviewer_keys)
    if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.:@/-]{1,128}", name)
           or type(key) is not bytes or not 32 <= len(key) <= 128
           for name, key in keys.items()):
        raise ValueError("INVALID_REVIEWER_KEYS")
    if len(set(keys.values())) != len(keys):
        raise ValueError("DUPLICATE_REVIEWER_KEY")

    def authorize(binding):
        # Freeze both request and receipt, independent of mutable transport objects.
        try:
            expected = json.dumps(binding,sort_keys=True,separators=(",",":"),allow_nan=False)
            if len(expected.encode("utf-8")) > 4096:
                raise ValueError("REVIEW_REQUEST_TOO_LARGE")
            response = request_receipt(json.loads(expected))
            encoded = json.dumps(response,sort_keys=True,separators=(",",":"),allow_nan=False)
            if len(encoded.encode("utf-8")) > 8192:
                raise ValueError("REVIEW_RECEIPT_TOO_LARGE")
            receipt = json.loads(encoded)
        except (TypeError, OverflowError, RecursionError) as error:
            raise ValueError("INVALID_REVIEW_RECEIPT") from error
        fields = {"schema","binding","reviewer_id","authorization_id","issued_at","expires_at",
                  "verification_authorized","approved","deployment_allowed","mac"}
        if not isinstance(receipt,dict) or set(receipt) != fields:
            raise ValueError("INVALID_REVIEW_RECEIPT")
        reviewer = receipt["reviewer_id"]
        if not isinstance(reviewer,str) or reviewer not in keys:
            raise ValueError("UNKNOWN_REVIEWER")
        if (receipt["schema"] != "review-hmac-sha256-v1"
                or receipt["binding"] != json.loads(expected)
                or receipt["verification_authorized"] is not True
                or receipt["approved"] is not False
                or receipt["deployment_allowed"] is not False
                or not isinstance(receipt["authorization_id"],str)
                or not re.fullmatch(r"[A-Za-z0-9_.:@/-]{1,128}",receipt["authorization_id"])):
            raise ValueError("REVIEW_AUTHORIZATION_DENIED")
        issued,expires = receipt["issued_at"],receipt["expires_at"]
        now = clock()
        if (type(issued) is not int or type(expires) is not int
                or not isinstance(now,(int,float)) or isinstance(now,bool)
                or not issued <= now < expires or not 0 < expires-issued <= 300):
            raise ValueError("REVIEW_RECEIPT_EXPIRED")
        mac = receipt.pop("mac")
        if not isinstance(mac,str) or not re.fullmatch(r"[0-9a-f]{64}",mac):
            raise ValueError("INVALID_REVIEW_MAC")
        payload = json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
        expected_mac = hmac.new(keys[reviewer],payload,"sha256").hexdigest()
        if not hmac.compare_digest(mac,expected_mac):
            raise ValueError("REVIEW_MAC_MISMATCH")
        return receipt
    return authorize
