# Preserving existing paper data: preflight only

This PR adds a read-only numeric-precision preflight for existing legacy
paper accounts and trades. It rejects values that would be rounded or
overflow the target PostgreSQL NUMERIC precision/scale.

**NOT a migration**: the prior revision intentionally refuses populated
tables. Before constructing a data-preserving migration, verify
currency assumptions, positive holdings, balances, fees, NULL constraints,
fence semantics, pre-existing active writers and real schema details.
Use pre-existing data fixtures to prove counts and values after migration,
and a fully separate restore/rollback drill.

The preflight is informational and not sufficient authorization to migrate.
Do not apply it on VPS without a reviewed read-only execution plan.
