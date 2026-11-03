# P0 release validator hardening — 2026-11-03

Parent: a369f045603e4fb6421f482135d3d967a6a5d55c, PR #128.

Reproduced fail-open static validation: appending USER 0, a whitespace/case variant, duplicate USER, pip/python -m pip/uv/apt installation, ONBUILD or SHELL, and chaining an additional install. Eleven new negative cases failed before the fix; all 25 tests pass after it.

The validator now accepts a deliberately narrow, single-line release recipe instruction set. Exactly one canonical USER 10001 is required. Exactly one hash-enforced pip installation is required; the sole other allowed RUN is the existing mkdir/chown setup, at most once. No RUN is allowed after USER. Parser syntax/escape overrides, ONBUILD, SHELL and other unsupported instruction types are rejected. It does not attempt to be a general Dockerfile parser or sandbox arbitrary application source.

Existing base digest, lock path, package pins/hashes, duplicate package and symlink checks remain. The actual release Dockerfile is unchanged. No new runtime module, duplicate worker/verifier/queue ownership, production changes, merge or VPS access.

Validation: 25 local release policy/regression tests passed; CI for this commit must be checked separately. Previous parent has 33 successful workflows and matching image IDs across two runners; this is not proof of final-commit CI or issue #90 acceptance.

Remaining issue #90 gates include current read-only VPS evidence, deployed-source reconciliation, restorable backup verification and isolated acceptance. approved=false and deployment_allowed=false remain required.
