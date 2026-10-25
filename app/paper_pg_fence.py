"""PostgreSQL-only transactional fence for hypothetical paper writers.

Not wired to the API; needs an approved schema migration and writer integration.
Every writer must lock the fence row BEFORE reading or changing paper balances.
"""
from sqlalchemy import text

def check_fence(con, generation: int):
    if con.dialect.name != "postgresql" or not con.in_transaction():
        raise PermissionError("POSTGRES_TRANSACTION_REQUIRED")
    row = con.execute(text(
        "SELECT mode, generation FROM paper_write_fence WHERE id=1 FOR UPDATE"
    )).first()
    if row is None or row.mode != "LEGACY" or row.generation != generation:
        raise PermissionError("PAPER_WRITES_FENCED")

def quiesce(con, *, generation: int, approved: bool = False):
    if not approved:
        raise PermissionError("APPROVAL_REQUIRED")
    check_fence(con, generation)
    con.execute(text(
        "UPDATE paper_write_fence SET mode='QUIESCED', generation=generation+1 WHERE id=1"
    ))
    return generation+1
