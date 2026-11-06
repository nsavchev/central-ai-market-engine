# Controlled worker rollout review

The [profile example](../../deploy/ai08/worker-review-profile.example.json) is a review artifact. No runtime entrypoint consumes it, and changing its enabled field cannot provision authority or activate a worker. Current operational evidence belongs in the protected operator record, separate from public source/CI. The [canonical register](PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md) owns progress.

## First operational profile

- Keep activation disabled and jobs empty until an operator independently authorizes a specific task/source/spec/test/image tuple. Completed acceptance tasks belong under evidence_jobs; they are not new pending work.
- Retain the selected provider/model, 128 output-token limit and existing bounded transport. No fallback provider/model. The provider key and separate durable reviewer key must remain outside the profile. Ephemeral acceptance keys are not production authority.
- Record the account's actual enforced monthly USD limit from private evidence. This is independent of application accounting and is not established by CI or an API key merely being configured.
- Use generation-admission-usd-v2 for a USD application policy: budget_limit_microusd and reserved_microusd are integer millionths of a US dollar. For example, 1,000,000 micro-USD is USD1. One admitted callback per UTC month is the initial conservative proposal; changing it needs a new explicit host policy. Reservations are declared ceilings, not verified model pricing or provider invoices. Failed/interrupted admissions are not refunded automatically.
- V1 receipts remain EUR and are never relabelled or converted. Mixed currencies in the same database/month are rejected. Keep acceptance databases intact. Choose and bind an operational ledger deliberately; never copy/delete/recreate a ledger to reset spent amounts or call counts. One application's ledger is not an account-wide cap; manual /ask and other databases/clients remain outside it.
- Freeze a reviewed source commit, runtime environment/image, independent harness and output directories. The verifier image digest is distinct from the worker/runtime source binding. An acceptance image is not proof of a deployed release.
- Reuse the existing worker/scheduler/service ownership. Proposed initial schedule: existing five-minute cadence, one cycle and max_tasks=1 per service run; 180-second service timeout is a proposal to review against worst-case transport/verifier cleanup time. No second timer or automatic activation. Existing CLI is analysis-only; an independently reviewed trusted entrypoint must construct/inject the handler before a review-enabled service can be installed.

## Stop and reconcile

1. Stop future service/timer starts using the explicitly reviewed service identity. Do not reuse an assumed unit name from a historical transcript or stop unrelated production services.
2. Allow bounded in-flight work/cleanup to settle and inspect the supervisor state and task verification journal. Killing a local process does not establish that the provider did not process a request.
3. Treat preparing/running/quarantined or uncertain dispatch as reconciliation-required. Keep nonce, allowance, spent reservation, attempt marker, candidate/test hashes and resource handles. No automatic requeue, revision, new case or fresh database.
4. Confirm cleanup by the recorded exact resource identities. Do not broadly remove Docker objects by a name prefix or delete unconfirmed resources from an untrusted report.
5. Any resumed review needs the retained journal, unchanged source/tests, valid independent authority and remaining budget. Completed/blocked reviews do not automatically dispatch again. Promotion remains approved=false/deployment_allowed=false.

## Activation gates still required

The finite worker acceptance is one synthetic arithmetic scenario. Before recurring use, reconcile private source/image/task/harness bindings, persist separate operator authority, provide a reviewed trusted handler entrypoint, validate the chosen ledger/currency policy and remaining funds, review service timeout/isolation/rollback, and approve a concrete single-service change. Do not activate merely because all CI checks or one finite real-provider test passed. No schema migration, arbitrary code execution, real orders or automatic deployment is included.
