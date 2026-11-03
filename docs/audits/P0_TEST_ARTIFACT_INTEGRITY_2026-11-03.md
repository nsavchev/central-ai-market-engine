# P0 test artifact integrity — 2026-11-03

Parent: 35a05f4d3f7880a671e8354232c5a6ad2f5b6729, PR #128. The existing functional verifier checked only candidate bytes while accepting tests by path. This patch adds a separate expected_test_sha256 gate and threads trusted_test_sha256 through the existing prepare_and_verify path. Missing/malformed digests or mismatched test bytes fail before Docker; the enabled pipeline rejects a missing digest before preparing artifacts. Disabled paths retain their disabled error. A successful verifier/pipeline report records the test digest. No alternate verifier, queue, scheduler or retry mechanism is added.

Callers must obtain the expected digest from their reviewed test source, independently of an untrusted candidate. Compatibility is intentionally fail-closed: an enabled caller that omits the new optional-at-signature parameter gets INVALID_TEST_HASH. Tests, full-process fixture and real functional/timeout CI call sites are updated. CI fixtures calculate their known local test digest; this is not independent authentication.

Local evidence: 74 tests passed across functional verifier, pipeline, full process, release policy and CI action provenance. Added regression cases ensure missing/malformed/tampered test hashes never call Docker. New commit CI remains to be checked.

## Limits and next blocker

This closes a missing integrity check, NOT trusted-author authentication. A caller controlling both bytes and expected digest can still supply arbitrary tests. Host bind paths are still mutable between hash checking and container start (TOCTOU). There is no signed test-author manifest, independently reviewed test registry, immutable input snapshot or signed persisted execution report. Do not label authenticated provenance complete or enable autonomous generated-code execution.

Next: define the trusted reviewer/source boundary for exact task/candidate/test/image tuple and freeze validated input bytes before the existing verifier execution. Keep any such work on isolated non-production infrastructure and keep cleanup_unconfirmed a quarantine stop. Production Docker is not a hardened hostile-code sandbox.

No merge, VPS changes, deployment, production DB writes or live trading. approved=false/deployment_allowed=false remain. Issue #90 still requires current deployed SHA/runtime/schema evidence, full review and disposable restore validation.
