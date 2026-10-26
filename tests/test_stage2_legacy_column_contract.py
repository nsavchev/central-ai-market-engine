from sqlalchemy import create_engine
from app.paper_legacy_column_contract import inspect_legacy_paper_columns

def test_read_only_paper_preflight_fails_closed_on_sqlite():
    engine = create_engine("sqlite:///:memory:")
    assert inspect_legacy_paper_columns(engine) == {
        "ready": False, "errors": ["POSTGRES_REQUIRED"]}
    engine.dispose()
