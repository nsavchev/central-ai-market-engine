# Durable paper cutover fence: limitations

A small SQLite prototype persists a monotonically increasing generation and
manual quiesce decision across restarts. The write check must run inside each
writer transaction to be effective.

**It does not currently protect the FastAPI or PostgreSQL ledger.** The old
Paper Trading API has not been instrumented to check this fence. In particular,
a SQLite fence checked separately from PostgreSQL cannot guarantee atomic
quiescence with in-flight PostgreSQL transactions. Production implementation
should store phase/generation in PostgreSQL and lock the same authoritative
row within the hypothetical-fill transaction, then prove that no legacy writer
can bypass the check. Continue to block the cutover until proven.

No real writer stoppage, migration, broker action or deployment is performed.
