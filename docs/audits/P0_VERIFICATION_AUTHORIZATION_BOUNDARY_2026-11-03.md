# P0 verification authorization boundary — 2026-11-03

Parent e30982e222934fb581064792abc0fbd1ffc7ca09, draft PR #128. Inspecting existing verifier_gate/review_handoff/verified_review_pipeline found review-state and hash gates, but no configured trusted identity/signing provider. Do not invent an approval authority or represent hashes as authentication.

## Implemented in the existing pipeline

prepare_and_verify now requires a trusted host-supplied authorization_check callable, absent by default. Missing dependency blocks before preparing artifacts. The existing preparation path creates review artifacts, then the authorizer receives a fresh request tuple: schema, nonce, task_id, candidate SHA256, test SHA256, digest-pinned image and verify_only scope. It must return explicit verification_authorized=true, the unchanged tuple, nonempty reviewer_id and authorization_id, and approved=false/deployment_allowed=false. Failure prevents calling the verifier. A fresh random nonce binds the response to the current invocation. Authorizer exceptions propagate, preventing execution. No user proposal is evaluated/imported as an authorizer.

Result records reviewer/authorization IDs and nonce; these records are transient like the existing pipeline result. There is no new queue, state controller, retry engine, signing service or database schema. Approval/deployment flags remain false.

## Trust and completion limits

authorization_check is a TRUSTED HOST DEPENDENCY like the existing injected verifier. It is not a self-authenticating receipt validator: anyone controlling Python callers can supply a fake callable. A reviewed deployment adapter must authenticate the reviewer and independently validate signature/authorization freshness, scope and exact tuple against trusted identity/key policy. No such adapter/key authority is configured by this change. The CI fake is explicitly synthetic. This change proves required fail-closed wiring and tuple binding, NOT authenticated human approval in production.

The low-level functional verifier remains available for explicitly authorized isolated fixtures and is not made into a global authorization service. No HTTP endpoint, scheduler or production execution is enabled. Host callers must not expose arbitrary dependency injection to untrusted requests.

## Validation

94 local tests passed: existing frozen-input/cleanup, release and action-provenance checks, full-process positive/negative fixtures plus missing authorizer, denied receipt, altered task/candidate/test/image/nonce/scope, approval/deployment escalation, missing reviewer/decision IDs, mutated request and stale receipt rejection. The positive full-process test uses ci-trusted-review-fixture and ci-only authorization IDs. Final-commit CI still requires review.

## Next checkpoint

Keep automated candidate execution disabled until a reviewed identity/signature adapter is connected from trusted configuration (not candidate input), with end-to-end authenticated evidence and persisted audit result. Current VPS SHA/runtime/schema inventory, restoration in a disposable environment and complete changed-file reconciliation remain mandatory under issue #90. No merge, VPS operation, production modification or live trading authorized.
