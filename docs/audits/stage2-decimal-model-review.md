# Stage 2 Decimal ORM model contract

PaperAccount.cash is now Numeric(20,2), PaperTrade.quantity Numeric(24,6),
and price/fee Numeric(20,2). Values are represented as Decimal in ORM.

**NOT DEPLOYABLE**. This model must *not* run against old Float-backed
production schema. Legacy /paper/trades and /paper/account still use floats:
legacy writes must be disabled and the reader adapted/tested before cutover.
The existing main.py legacy guard depends on PAPER_V2_ENABLED being YES,
which is not a reliable standalone cutover barrier. Bootstrap and migration
require an independently reviewed full deployment sequence.

Main app startup currently calls init_db and has no production Alembic
revision baseline. This change does not fix it. This branch is an isolated
review of ORM column types, not an approved release.
