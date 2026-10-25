# A04 precise NUMERIC schema gate

The previous baseline inventory checked type names only. PostgreSQL allows
unbounded NUMERIC, and the atomic paper service assumes fixed cent/share
scales. This read-only check verifies BOTH precision and scale of canonical
columns.

Required: cash NUMERIC(20,2), quantity NUMERIC(24,6), price NUMERIC(20,2),
fee NUMERIC(20,2). Shadow columns alone do not satisfy the contract.

This audit check returns deployment_authorized=false even if the schema
passes. It does NOT inspect actual deployed data, constraints, owner roles,
backup recovery, or applied Alembic revisions. Human approval remains
necessary. No migrations, database mutations, or real trading.
