# Controlled worker rollout review

The [profile example](../../deploy/ai08/worker-review-profile.example.json) is a review artifact. No runtime entrypoint consumes it, and changing its enabled field cannot provision authority or activate a worker. Current operational evidence belongs in the protected operator record, separate from public source/CI. The [canonical register](PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md) owns progress.

## First operational profile

- Keep activation disabled and jobs empty until an operator independently authorizes a specific task/source/spec/test/image tuple. Completed acceptance tasks belong under evidence_jobs; they are not new pending work.
- Retain the selected provider/model, 128 output-token limit and existing bounded transport. No fallback provider/model. The provider key and separate durable reviewer key must remain outside the profile. Ephemeral acceptance keys are not production authority.
- Record the account's actual enforced monthly USD limit from private evidence. This is independent of application accounting and is not established by CI or an API key merely being configured.
- Use generation-admission-usd-v2 for a USD application policy: budget_limit_microusd and reserved_microusd are integer millionths of a US dollar. For example, 1,000,000 micro-USD is USD1. One admitted callback per UTC month is the initial conservative proposal; changing it needs a new explicit host policy. Reservations are declared ceilings, not verified model pricing or provider invoices. Failed/interrupted admissions are not refunded automatically.
- V1 receipts remain EUR and are never relabelled or converted. Mixed currencies in the same database/month are rejected. Keep acceptance databases intact. Choose and bind an operational ledger deliberately; never copy/delete/recreate a ledger to reset spent amounts or call counts. One application's ledger is not an account-wide cap; manual /ask and other databases/clients remain outside it.
- Freeze a reviewed source commit, runtime environment/image, independent harness and output directories. The verifier image digest is distinct from the worker/runtime source binding. An acceptance image is not proof of a deployed release.
- Reuse the existing worker/scheduler/service ownership. Proposed initial schedule: existing five-minute cadence, one cycle and max_tasks=1 per service run; 180-second service timeout is a proposal to review against worst-case transport/verifier cleanup time. No second timer or automatic activation. The CLI remains analysis-only by default. Review mode requires CENTRAL_SUPERVISED_SERVICE_ENABLED=YES, CENTRAL_WORKER_REVIEW_ENABLED=YES and CENTRAL_WORKER_REVIEW_CONFIG pointing to a complete trusted runtime policy; installing/enabling a service remains an independent operational action.

## Stop and reconcile

1. Stop future service/timer starts using the explicitly reviewed service identity. Do not reuse an assumed unit name from a historical transcript or stop unrelated production services.
2. Allow bounded in-flight work/cleanup to settle and inspect the supervisor state and task verification journal. Killing a local process does not establish that the provider did not process a request.
3. Treat preparing/running/quarantined or uncertain dispatch as reconciliation-required. Keep nonce, allowance, spent reservation, attempt marker, candidate/test hashes and resource handles. No automatic requeue, revision, new case or fresh database.
4. Confirm cleanup by the recorded exact resource identities. Do not broadly remove Docker objects by a name prefix or delete unconfirmed resources from an untrusted report.
5. Any resumed review needs the retained journal, unchanged source/tests, valid independent authority and remaining budget. Completed/blocked reviews do not automatically dispatch again. Promotion remains approved=false/deployment_allowed=false.

## Activation gates still required

The finite worker acceptance is one synthetic arithmetic scenario. Before recurring use, reconcile private source/image/task/harness bindings, persist separate operator authority, provide a reviewed trusted handler entrypoint, validate the chosen ledger/currency policy and remaining funds, review service timeout/isolation/rollback, and approve a concrete single-service change. Do not activate merely because all CI checks or one finite real-provider test passed. No schema migration, arbitrary code execution, real orders or automatic deployment is included.


## Runtime policy and persistent authority

The separate [runtime example](../../deploy/ai08/worker-review-runtime.example.json) uses worker-review-runtime-v1. Its disabled placeholders are intentionally rejected. The loader never converts a review profile into executable permissions. Policy and raw reviewer key must be regular, singly linked, owner-only files owned by the service identity, inside owner-only directories, with canonical absolute paths. Keep them outside ledger/source/artifact storage. No inline credential is accepted. Duplicate JSON keys, unsafe permissions, mismatched database, unknown fields, incomplete grants and changed core-file hashes fail closed. An absent model key fails before any reservation.

Provision a raw 32-byte reviewer key only with the explicit existing verifier_gate.provision_reviewer_key(enabled='YES', path=...) operation after its private parent directory exists. It uses exclusive creation and syncs the result, returns only safe creation metadata, and refuses overwrite. A restart reads the same key rather than generating a new identity. Key provisioning does not grant any task or start work. The key authenticates a host-scoped HMAC reviewer role; it is not evidence of a separate human or external review service.

The operator-owned runtime policy grants only listed task IDs, fixed source/spec/test/image tuples, the reviewed OpenAI model, at most 128 output tokens and one admitted callback per UTC month. It does not allow automatic revision tasks. Before constructing a handler, the loader rechecks target registration, source and independent harness hashes, false promotion flags and eight core Python file hashes. Those core hashes are not a complete release/image attestation; remaining runtime dependencies and deployment identity still need the operational release checks. Separate generation and verify-only receipts are issued from these host grants. Verification continues through the existing HMAC authorizer and bounded Docker verifier. USD reservations remain declared ceilings, not invoices. No schema migration, counter reset, deployment or timer enable occurs in the loader.


## Disabled preparation and validation

load_worker_review_config(..., validation_only=True) accepts a fully specified runtime policy with execution_authorized=false and returns only a validation report. It performs the same private-file/core/grant/key checks, but never constructs a provider or callable worker handler, requires no model credential and does not write the database. Default live loading still rejects disabled execution. Validation does not prove provider account access or model/image availability.

The existing operator script's --prepare-runtime mode stages a separately pinned source bundle into a new exclusive private state directory and reuses an explicitly selected existing virtualenv without dependency installation. It reads the existing private reviewer key, creates one newly identified public arithmetic pilot task through the actual bridge/target registry, writes an exclusive disabled policy and invokes validation-only. The task remains planned/pending with zero acquired attempts and no generation admission. This is deliberate initial preparation of a separate operational USD ledger, not a retry/reset/copy of spent acceptance history. Keep all old acceptance cases and partial preparation directories; do not choose fresh paths to bypass an error. The fixed call ceiling is one per UTC month; reservations are declared amounts, not invoices.

No key is regenerated/copied, no model key is fetched, no Docker image is pulled and no provider/worker/timer starts during preparation. The selected verifier digest is bound as policy metadata; validation alone does not inspect the image. The policy remains execution_authorized=false and requires a separate concrete operational review before enabling any work. A prepared source directory is staging, not service deployment or release attestation.
