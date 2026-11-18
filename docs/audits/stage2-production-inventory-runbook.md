# Stage 2 production read-only inventory — operator runbook

**This PR does not connect to, inspect or modify the VPS.** The SQL in
`docs/audits/stage2-production-inventory.sql` is a reviewable, read-only
inventory. It is intended for an operator to execute under a read-only
PostgreSQL role, after verifying the database target. It does not collect
financial rows or secrets; it includes counts, column definitions, indexes,
constraints and identity/default metadata.

## Next required steps

1. Verify the running deployment and identify the actual PostgreSQL target
   without exposing credentials or changing the stack.
2. Obtain the schema inventory from a read-only session; keep results private.
3. Compare it with the original deployed ORM, migrated ORM and full Alembic
   DDL. In particular confirm `id` sequences/defaults and the differences
   between `LEGACY` and `QUIESCED` writer fences.
4. Verify fresh, independent backup and restore before any write or stamp.
5. Prepare a separate production migration with preflight, lock timeout,
   explicit approval and rollback plan. Never run CI fixture tests on VPS.

**Unresolved:** Current Alembic environment and migrations are deliberately
restricted to the disposable DB named `test`. Passing tests is not release
approval. The user has not granted authorization for schema updates on
`market`, deployment, or merges.


## Generic restricted-runtime rehearsal (DB-ACL-REHEARSAL-01)

This is a source-derived proposal, not a record of any current deployment's
roles or configuration. Do not execute role-creating fixture tests on the VPS.
The existing `tests/test_stage2_baseline_postgres.py` and existing baseline CI
job own this rehearsal, restricted to an explicitly enabled disposable local
PostgreSQL database named `test` with an initially empty public schema.

The test creates a random, independent LOGIN with no memberships and
NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS/NOINHERIT.
It grants CONNECT, schema USAGE, USAGE on the five known serial sequences,
and the following table permissions, without object ownership or grant option:

| Existing table | Proposed permissions | Source owner requiring writes |
|---|---|---|
| instruments | SELECT, INSERT | main.ingest instrument creation |
| daily_bars | SELECT, INSERT, UPDATE | main.ingest insert/update existing bars |
| financial_snapshots | SELECT, INSERT, UPDATE | fundamentals_history.store_snapshot |
| paper_accounts | SELECT, INSERT, UPDATE | legacy paper handler / explicit account bootstrap |
| paper_trades | SELECT, INSERT | paper ledger append |

A fresh authenticated connection commits synthetic inserts with serial IDs,
FKs and updates, then independently reads them back. Other cases require
PostgreSQL insufficient_privilege (42501) for DELETE on each table, TRUNCATE,
unneeded instrument/trade UPDATE, persistent public-schema CREATE/ALTER/DROP,
sequence ALTER/setval, role creation, self-promotion and SET ROLE to the
provisioner. This does not use SET ROLE from a superuser session to simulate
isolation. Test roles/connections/grants and fixture objects are cleaned up.

Scope limits: this exercises a curated legacy schema and SQL operation shapes,
not exact deployed API HTTP behavior, RLS/tenant isolation, all inherited PUBLIC
rights, network/HBA policy or a future migrated schema. PostgreSQL PUBLIC TEMP
rights are not globally revoked by this test. It grants no privileges on future
objects and provisions no production credential. Current runtime modules,
Compose and migrations are unchanged; application bootstrap is not invoked.

### Separate acceptance and rollback before an API credential change

1. Resolve exact deployed source/image identity privately and compare its DB
   callers, startup DDL and flags against the reviewed candidate. In candidate
   source, PostgreSQL lifespan refuses startup without the explicit managed-schema
   setting and does not call create_all. Do not set that flag merely to bypass a
   legacy schema/migration gate or infer that the deployed image has this behavior.
2. Rehearse the exact approved image against a separate restored-copy schema with
   an independent runtime login; test health, auth/negative cases and authorized
   DB consumers. Use synthetic data and no production mounts or provider keys.
   Existing source permissions and paper-mode gates continue to apply.
3. Review schema/function/PUBLIC privileges, role memberships, effective grants,
   sequence access and all actual writers. Keep object ownership and migration
   administration on a separate role. Do not demote an existing shared admin or
   add broad ALL/default grants to silence errors. Missing access fails closed.
4. Prepare an exact API-only credential cutover and protected previous
   configuration/image reference. Obtain separate production authorization after
   the role setup, grants and rollback procedure are concrete and reviewed.
5. After an approved cutover, check health and DB identity/privileges from the API
   connection. If it fails, restore only the previous approved API configuration;
   do not alter schema, restore DB data, drop shared roles or activate workers as
   an improvised rollback. Previous admin credentials remain protected, not
   published in scripts, shell history or GitHub artifacts.

No production role/grant SQL or runnable deployment command is provided by this
rehearsal. Operational findings stay outside public source documentation.


## Disposable exact-image driver (DB-IMAGE-ACCEPTANCE-01)

`scripts/market_role_image_rehearsal.py` is an operator-run acceptance utility,
not an application manager or a deployment command. It takes explicit local
immutable API/PostgreSQL image IDs, a reviewed Python-source manifest checksum,
and a checksum-verified existing schema fixture. It does not inspect deployed
containers, copy their environment or use their database/network/volumes.
No image pull or build is performed by the utility.

It creates one internal network and two randomly named, labelled test containers.
The PostgreSQL 16 cluster uses a bounded RAM filesystem and fresh disposable
admin/runtime credentials. The API receives only runtime credentials and a
synthetic API token, runs nonroot with a read-only root, dropped capabilities,
no host ports/mounts, and CPU/memory/PID bounds. Implicit API volumes and unreviewed
baked environment keys are refused. Environment files are private temporary
files. Images are trusted operator-selected application images, not arbitrary
model-generated code; this is not a hardened hostile-code sandbox.

Before application import, the API clone must match the supplied source manifest
and contain no .env files at the checked application locations. A mismatch stops
acceptance; never copy a changed production file into the test image to force a
match. Tests then exercise the independent login, actual lifespan without DDL,
health/auth, synthetic paper fill, permission-aware manual history insert/update,
legacy ORM bar/instrument writes and privilege denials. They issue no broker,
SEC or other external-provider request. The scenario is deliberately a legacy
Float-schema compatibility test; it does not promote a Numeric migration or
claim complete API/strategy/security acceptance.

Cleanup operates only on reserved names carrying this run's exact label, proves
container absence and removes an empty owned network. Wrong ownership, a retained
container, connected network or Docker uncertainty blocks success. No broad prune,
production restart, role demotion, schema update or credential cutover exists.
Normal failure/timeouts trigger cleanup. SIGKILL/host/daemon failure can prevent
cleanup; review labelled test resources before rerunning. Credentials are only
for the new disposable cluster. A restored-copy rehearsal and separate rollout
review are still required before production changes.

The existing baseline workflow owns unit guard/cleanup fault injection and a real
Docker integration. CI builds a historical public-source fixture using the pinned
Python base from release/Dockerfile.release, then passes its local image ID and
the existing PostgreSQL 16 image ID. This CI fixture has resolved test dependencies,
not a production lock/build attestation or evidence about any operator image.
An operator run must use the actual separately reviewed image and manifest.

Standalone operator preparation: download the utility and existing schema fixture
from one immutable reviewed commit into a private temporary directory and verify
both file SHA256 values before running. Pass image IDs, not tags; do not supply a
production connection URL, credentials or volume. Success requires both
isolated_api_acceptance=passed and cleanup_confirmed=true. Keep actual operational
identifiers/results in protected evidence, not public source documentation.


## Prepare-only credential review files (DB-ENV-PREPARE-01)

After the exact-image restricted-login rehearsal, use
`scripts/market_role_cutover_prepare.py --api-container <reviewed-container>
--base-compose <absolute-single-base-file> --output-parent <private-directory>`.
The output parent must belong to the current operator and have no group/other
permissions. The selected service must be the Compose api service with that
single base file and working directory. This scoped utility expects the reviewed
loopback-only HTTP binding; it refuses unexpected configuration.

The utility reads Docker metadata and runs Compose config only. It writes a new
0700 directory with four 0600 files: runtime.compose.yml, rollback.compose.yml,
role.sql and review.json. It preserves the existing API image by ID and all
reviewed app settings while removing the shared env_file and admin password from
the proposed runtime API environment. It validates other services remain unchanged
and that rollback restores the prior API environment. Dollar escaping is tested
with real Compose; no admin credential is printed.

The SQL is a review artifact, never automatically executed. It creates only a
fresh independent login with the tested five-table/sequence grants and rejects
unexpected effective schema/table privileges transactionally. It does not change
owners, demote an existing role, revoke global PUBLIC grants or add future-object
grants. This is not a full function/PUBLIC privilege audit.

Keep all four files private, including rollback and role.sql. Before any approved
application, recheck source-file hashes, image/container identities and schema/ACL
assumptions; review the exact SQL and prepare health/auth/new-role/negative checks.
Only an API-only recreation is in the proposed scope. Protected rollback must use
the same pinned image; it is not a DB restore. No executable apply/rollback helper
is included and bundle creation grants no production authorization.

