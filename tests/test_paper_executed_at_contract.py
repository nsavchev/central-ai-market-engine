"""Guard the simulated fill INSERT against the live NOT NULL timestamp contract."""
from pathlib import Path


def test_paper_v2_insert_supplies_executed_at():
    source = Path("app/paper_atomic_service.py").read_text()
    assert "INSERT INTO paper_trades(account_id,symbol,side,quantity,price,fee,executed_at)" in source
    assert "VALUES (:id,:symbol,:side,:quantity,:price,:fee,CURRENT_TIMESTAMP)" in source
