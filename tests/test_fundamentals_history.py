import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base, FinancialSnapshot
from app.fundamentals import Financials
from app.fundamentals_history import store_snapshot, history_report, annual_cagr

@pytest.fixture
def db():
    eng=create_engine('sqlite://')
    Base.metadata.create_all(eng)
    with Session(eng) as session: yield session
    eng.dispose()

def sample(year, revenue=100):
    return Financials(symbol='DEMO',period_end=f'{year}-12-31',period_type='FY',currency='USD',source='manual',units='ones',revenue=revenue,net_income=10,operating_income=15,invested_capital=60,income_tax=2,pretax_income=12,total_debt=20,cash=5,shareholders_equity=50,operating_cash_flow=20,capital_expenditure=5)

def test_cagr():
    assert annual_cagr(100,121,2)==10
    assert annual_cagr(-100,121,2) is None

def test_store_and_report(db):
    store_snapshot(db,sample(2023,100));store_snapshot(db,sample(2024,110));store_snapshot(db,sample(2025,121));db.commit()
    r=history_report(db,'DEMO','USD','manual')
    assert r['records']==3
    assert r['trends']['revenue_cagr_pct']==pytest.approx(10,abs=.02)
    assert r['financial_health']['debt_to_equity']==.4

def test_idempotent_import(db):
    store_snapshot(db,sample(2024,100));store_snapshot(db,sample(2024,200));db.commit()
    assert db.query(FinancialSnapshot).count()==1
    assert history_report(db,'DEMO','USD','manual')['records']==1

def test_reject_unapproved_source(db):
    with pytest.raises(PermissionError): store_snapshot(db,sample(2024).model_copy(update={'source':'investolens'}))

def test_missing_year_warning(db):
    store_snapshot(db,sample(2021));store_snapshot(db,sample(2025));db.commit()
    assert any('Missing fiscal years' in x for x in history_report(db,'DEMO','USD','manual')['warnings'])


def quality_item(**changes):
    data = dict(symbol='DEMO', period_end='2025-12-31', period_type='FY',
                currency='USD', source='manual', units='ones',
                accounting_standard='US_GAAP', retrieved_at='2026-10-25T00:00:00Z',
                revenue='100.125', total_assets=100, total_liabilities=40,
                shareholders_equity=60)
    data.update(changes)
    return Financials(**data)


def test_quality_metadata_and_decimal_text_survive_persistence(db):
    store_snapshot(db, quality_item())
    db.commit()
    row = db.query(FinancialSnapshot).one()
    assert row.payload['units'] == 'ones'
    assert row.payload['accounting_standard'] == 'US_GAAP'
    assert row.payload['retrieved_at'].startswith('2026-10-25T00:00:00')
    assert row.payload['total_liabilities'] == '40'
    assert row.payload['revenue'] == '100.125'


@pytest.mark.parametrize('changes,code', [
    ({'units': None}, 'UNITS_UNCONFIRMED'),
    ({'total_liabilities': 20}, 'BALANCE_MISMATCH'),
    ({'period_end': '2099-12-31'}, 'FUTURE_PERIOD'),
])
def test_quality_rejection_precedes_all_database_access(changes, code):
    from unittest.mock import MagicMock
    forbidden = MagicMock()
    with pytest.raises(ValueError, match=code):
        store_snapshot(forbidden, quality_item(**changes))
    assert not forbidden.mock_calls


def test_source_permission_precedes_quality_validation():
    from unittest.mock import MagicMock
    forbidden = MagicMock()
    with pytest.raises(PermissionError):
        store_snapshot(forbidden, quality_item(source='investolens', units=None))
    assert not forbidden.mock_calls


def test_sec_normalizer_output_cannot_bypass_manual_source_permission():
    from unittest.mock import MagicMock
    forbidden = MagicMock()
    with pytest.raises(PermissionError):
        store_snapshot(forbidden, quality_item(source='sec_edgar'))
    assert not forbidden.mock_calls


def test_rejected_update_preserves_existing_snapshot(db):
    store_snapshot(db, quality_item())
    db.commit()
    original = dict(db.query(FinancialSnapshot).one().payload)
    db.commit()  # End the read transaction before the explicit update transaction.
    with pytest.raises(ValueError, match='BALANCE_MISMATCH'):
        with db.begin():
            store_snapshot(db, quality_item(total_liabilities=20))
    assert db.query(FinancialSnapshot).one().payload == original


def test_bad_second_record_rolls_back_the_whole_batch(db):
    with pytest.raises(ValueError, match='UNITS_UNCONFIRMED'):
        with db.begin():
            store_snapshot(db, quality_item())
            store_snapshot(db, quality_item(period_end='2024-12-31', units=None))
    assert db.query(FinancialSnapshot).count() == 0


def seed_legacy(db, payload):
    from datetime import date
    row = FinancialSnapshot(symbol='DEMO', period_end=date(2025, 12, 31),
                            period_type='FY', currency='USD', source='manual', payload=payload)
    db.add(row)
    db.commit()
    return row.id


def test_legacy_unknown_units_remain_unchanged_and_require_verified_reimport(db):
    payload = quality_item().model_dump(mode='json')
    for key in ('units', 'accounting_standard', 'retrieved_at', 'total_liabilities'):
        payload.pop(key, None)
    row_id = seed_legacy(db, payload)
    with pytest.raises(ValueError, match='UNITS_UNCONFIRMED'):
        history_report(db, 'DEMO', 'USD', 'manual')
    assert db.get(FinancialSnapshot, row_id).payload == payload
    store_snapshot(db, quality_item())
    db.commit()
    assert db.query(FinancialSnapshot).count() == 1
    assert db.query(FinancialSnapshot).one().id == row_id
    assert history_report(db, 'DEMO', 'USD', 'manual')['units'] == 'ones'


def test_legacy_balance_mismatch_is_not_used_for_history_metrics(db):
    seed_legacy(db, quality_item(total_liabilities=20).model_dump(mode='json'))
    with pytest.raises(ValueError, match='BALANCE_MISMATCH'):
        history_report(db, 'DEMO', 'USD', 'manual')


def test_legacy_payload_identity_mismatch_cannot_be_reported_as_another_company(db):
    seed_legacy(db, quality_item(symbol='OTHER').model_dump(mode='json'))
    with pytest.raises(ValueError, match='FINANCIAL_SNAPSHOT_IDENTITY_MISMATCH'):
        history_report(db, 'DEMO', 'USD', 'manual')


def test_quality_review_warnings_remain_visible_in_history(db):
    store_snapshot(db, quality_item(accounting_standard=None, retrieved_at=None))
    db.commit()
    report = history_report(db, 'DEMO', 'USD', 'manual')
    assert any('ACCOUNTING_BASIS_UNCONFIRMED' in warning for warning in report['warnings'])
    assert any('MISSING_RETRIEVAL_TIME' in warning for warning in report['warnings'])


def test_cli_invalid_metadata_rejects_before_database_creation(tmp_path):
    import json
    import subprocess
    import sys
    input_path, database, output = tmp_path/'input.json', tmp_path/'history.db', tmp_path/'report.json'
    input_path.write_text(json.dumps([quality_item(units=None).model_dump(mode='json')]))
    output.write_text('previous report')
    result = subprocess.run([sys.executable, '-m', 'app.history_cli', str(input_path),
                             '--database', f'sqlite:///{database}', '--output', str(output)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert 'UNITS_UNCONFIRMED' in result.stderr
    assert not database.exists()
    assert output.read_text() == 'previous report'


def test_cli_demo_is_explicit_and_produces_verified_history(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path
    database, output = tmp_path/'history.db', tmp_path/'report.json'
    demo = Path('data/demo_financial_history.json')
    assert all(row['units'] == 'ones' for row in json.loads(demo.read_text()))
    result = subprocess.run([sys.executable, '-m', 'app.history_cli', str(demo),
                             '--database', f'sqlite:///{database}', '--output', str(output)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report['records'] == 5 and report['units'] == 'ones'


def test_cli_failed_legacy_report_rolls_back_new_imports(tmp_path):
    import json
    import subprocess
    import sys
    database, input_path, output = tmp_path/'history.db', tmp_path/'input.json', tmp_path/'report.json'
    engine = create_engine(f'sqlite:///{database}')
    Base.metadata.create_all(engine)
    legacy = quality_item().model_dump(mode='json')
    legacy.pop('units')
    with Session(engine) as session:
        seed_legacy(session, legacy)
    input_path.write_text(json.dumps([quality_item(period_end='2024-12-31').model_dump(mode='json')]))
    result = subprocess.run([sys.executable, '-m', 'app.history_cli', str(input_path),
                             '--database', f'sqlite:///{database}', '--output', str(output)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode != 0 and 'UNITS_UNCONFIRMED' in result.stderr
    assert not output.exists()
    with Session(engine) as session:
        assert session.query(FinancialSnapshot).one().payload == legacy
    engine.dispose()


def test_real_postgres_quality_rollback_and_json_metadata():
    import os
    import uuid
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    raw = os.getenv('TEST_POSTGRES_URL')
    if not raw:
        if os.getenv('CI'):
            pytest.fail('Disposable PostgreSQL URL required in CI')
        pytest.skip('Disposable PostgreSQL URL not supplied locally')
    url = make_url(raw)
    if url.get_backend_name() != 'postgresql' or url.database != 'test' or url.host not in ('127.0.0.1', 'localhost'):
        pytest.fail('REFUSE_NON_DISPOSABLE_POSTGRES_DATABASE')
    engine = create_engine(url)
    schema = 'financial_quality_ci_' + uuid.uuid4().hex
    created = False
    try:
        with engine.begin() as con:
            con.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        scoped = engine.execution_options(schema_translate_map={None: schema})
        FinancialSnapshot.__table__.create(scoped)
        with Session(scoped) as session:
            with pytest.raises(ValueError, match='BALANCE_MISMATCH'):
                with session.begin():
                    store_snapshot(session, quality_item())
                    store_snapshot(session, quality_item(period_end='2024-12-31', total_liabilities=20))
            assert session.query(FinancialSnapshot).count() == 0
            session.rollback()
            with session.begin():
                store_snapshot(session, quality_item())
            row = session.query(FinancialSnapshot).one()
            assert row.payload['units'] == 'ones' and row.payload['revenue'] == '100.125'
            original = dict(row.payload)
            session.rollback()
            with pytest.raises(ValueError, match='UNITS_UNCONFIRMED'):
                with session.begin():
                    store_snapshot(session, quality_item(units=None))
            assert session.query(FinancialSnapshot).one().payload == original
    finally:
        if created:
            with engine.begin() as con:
                con.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
