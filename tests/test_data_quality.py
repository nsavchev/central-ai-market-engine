from datetime import date
from app.data_quality import check_snapshot, compare_sources

BASE={'symbol':'DEMO','source':'licensed_demo','currency':'USD','period_type':'FY',
      'period_end':'2025-12-31','units':'ones','accounting_standard':'US_GAAP',
      'retrieved_at':'2026-01-20T00:00:00Z','total_assets':1000,
      'total_liabilities':600,'shareholders_equity':400,'revenue':1000,
      'shares_diluted':100,'operating_cash_flow':200,'capital_expenditure':30}
def test_clean():
    assert check_snapshot(BASE,as_of=date(2026,10,18))['status']=='passed'
def test_missing_units_blocks():
    assert check_snapshot({**BASE,'units':None},as_of=date(2026,10,18))['status']=='blocked'
def test_balance_mismatch_blocks():
    assert 'BALANCE_MISMATCH' in [i['code'] for i in check_snapshot({**BASE,'total_liabilities':500})['issues']]
def test_future_blocks():
    assert check_snapshot({**BASE,'period_end':'2030-01-01'})['status']=='blocked'
def test_negative_fcf_not_automatically_blocked():
    assert check_snapshot({**BASE,'operating_cash_flow':-100})['eligible_for_valuation']
def test_compare_same_basis():
    assert compare_sources([BASE,{**BASE,'source':'other','revenue':1010}],'revenue')['status']=='consistent'
def test_compare_conflict():
    assert compare_sources([BASE,{**BASE,'source':'other','revenue':1500}],'revenue')['status']=='conflict'
def test_compare_different_currency():
    assert compare_sources([BASE,{**BASE,'currency':'EUR'}],'revenue')['status']=='incomparable'
def test_bad_number():
    assert check_snapshot({**BASE,'revenue':'NaN'})['status']=='blocked'
