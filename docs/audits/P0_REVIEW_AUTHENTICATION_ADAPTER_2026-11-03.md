# P0 shared-key review authentication adapter — 2026-11-03

Parent 1603a8baa144f098778d1037e67396baa3603110, PR #128. Added make_hmac_review_authorizer in existing central_ai/verifier_gate.py; it plugs into the existing authorization_check dependency of prepare_and_verify. No new module, queue, verifier process, network client, identity service or dependencies.

## Implemented contract

Trusted host configuration supplies a mapping reviewer ID -> secret bytes (32..128 bytes) and a trusted request_receipt transport callable. Empty/weak/malformed mappings or duplicate reviewer keys fail. Configuration is captured privately, not looked up in candidate content or untrusted request parameters. No default keys or network endpoint; this code neither generates nor provisions production keys nor signs decisions.

The transport receives the exact current verification request (fresh nonce, task, candidate/test hashes, image, verify_only scope). The receipt is frozen via bounded canonical JSON. Exact receipt fields: schema review-hmac-sha256-v1, binding, reviewer_id, authorization_id, issued_at, expires_at, verification_authorized, approved, deployment_allowed and mac. The MAC is HMAC-SHA256 over UTF-8 JSON of all fields except mac, sorted keys, separators comma/colon, allow_nan=false. Unknown/extra fields fail. issued_at/expires_at must be integers, not booleans; issued_at <= current time < expires_at and validity <=300 seconds. Scope/tuple must match; verification only, approved=false/deployment_allowed=false.

Compare MAC with hmac.compare_digest as documented by Python: https://docs.python.org/3/library/hmac.html . IDs and decisions are authenticated by the configured shared key; no secret is returned in reports.

## Trust limits and activation

HMAC authenticates possession of a shared secret; both reviewer service and runner verifier can produce MACs. It is NOT a non-repudiable public-key signature or independent proof a named human reviewed the code. Reviewer identity depends on trusted provisioning and separation of duties. Only reviewed trusted host code may select reviewer keys/transport; arbitrary Python callers remain inside this trusted boundary.

No real reviewer service, endpoint, key storage, key provisioning/rotation/revocation workflow, clock synchronization, secret distribution or production identity is configured here. Revocation requires rebuilding the adapter without that reviewer key; captured configuration is intentionally stable within an instance. Tests use random ephemeral in-memory keys only. End-to-end production authentication remains NOT VERIFIED and execution must remain disabled until a real trusted provider is provisioned and tested separately.

## Validation and next gate

108 local tests passed across verifier gate, frozen functional verifier, authorization pipeline, full-process fixture, release policy and action provenance. Tests reject modified payload/MAC, wrong key, unknown reviewer, expired/future/long-lived receipt, boolean time, wrong binding, deployment escalation and malformed MAC; positive synthetic receipt travels through the existing pipeline. New-commit CI must be checked.

Next decision requires operator-owned reviewer identity and secret-management/provider boundary outside the repository. Do not paste secret keys into chat or commit them. Before activation: review that boundary, demonstrate authenticated approval of exact input tuple, persist the audit result, enforce quarantine on cleanup uncertainty and complete issue #90 deployed-SHA/runtime/schema/restore evidence. No merge, VPS changes, production execution or live trading authorized.
