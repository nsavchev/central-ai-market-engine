# Combined A04 database readiness

The combined read-only report composes the baseline inventory from PR #43 and
precision/scale contract from PR #44. It does not connect to a database on its
own; a caller must supply a PostgreSQL engine with read-only permissions.

`STRUCTURAL_CHECKS_PASSED` means only that version metadata and required
canonical NUMERIC column types are structurally compatible. It **does not**
mean the actual data are reconciled or that rollback, approval, application
compatibility, or backup restoration have been tested.

Deployment authorization is always false. Missing Alembic baseline, wrong
type or precision, multiple revision heads, and missing columns block.
No production migration, table mutation, VPS action or trading is included.
