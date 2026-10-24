"""Deterministic financial-data quality checks. No scraping or broker orders."""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

MONETARY = ('revenue','net_income','operating_income','total_assets','total_liabilities',
            'shareholders_equity','cash','total_debt','operating_cash_flow','capital_expenditure')
VALID_PERIODS = {'FY','Q','TTM'}

def _number(value: Any):
    if value is None or isinstance(value,bool): return None
    try:
        d=Decimal(str(value))
        return d if d.is_finite() else None
    except (InvalidOperation,ValueError,TypeError): return None

def _issue(code, severity, message, field=None):
    return {'code':code,'severity':severity,'field':field,'message':message}

def check_snapshot(snapshot: dict, *, as_of: date | None = None) -> dict:
    """Block unusable records; warn about suspicious but possibly valid accounting."""
    as_of=as_of or date.today()
    issues=[]
    for field in ('symbol','source','currency','period_type','period_end'):
        if not snapshot.get(field): issues.append(_issue('MISSING_REQUIRED','block',f'Missing {field}',field))
    currency=snapshot.get('currency')
    if currency and (not isinstance(currency,str) or len(currency)!=3 or not currency.isalpha()):
        issues.append(_issue('INVALID_CURRENCY','block','Use three-letter ISO currency code','currency'))
    period=snapshot.get('period_type')
    if period and period not in VALID_PERIODS:
        issues.append(_issue('INVALID_PERIOD','block','Unknown financial reporting period','period_type'))
    raw_date=snapshot.get('period_end')
    try:
        end=date.fromisoformat(raw_date) if isinstance(raw_date,str) else raw_date
        if not isinstance(end,date): raise ValueError()
        if end>as_of: issues.append(_issue('FUTURE_PERIOD','block','Period end is in the future','period_end'))
        if (as_of-end).days>550: issues.append(_issue('OLD_PERIOD','warning','Historical period; do not treat as latest','period_end'))
    except (ValueError,TypeError):
        issues.append(_issue('INVALID_DATE','block','Period end must be ISO date','period_end'))
    units=snapshot.get('units')
    if units not in ('ones','thousands','millions','billions'):
        issues.append(_issue('UNITS_UNCONFIRMED','block','Explicit monetary units are required','units'))
    basis=snapshot.get('accounting_standard')
    if basis not in ('US_GAAP','IFRS','OTHER'):
        issues.append(_issue('ACCOUNTING_BASIS_UNCONFIRMED','warning','Accounting standard not verified','accounting_standard'))
    if not snapshot.get('retrieved_at'):
        issues.append(_issue('MISSING_RETRIEVAL_TIME','warning','Missing point-in-time retrieval timestamp','retrieved_at'))
    for field in MONETARY + ('shares_diluted',):
        val=snapshot.get(field)
        if val is not None and _number(val) is None:
            issues.append(_issue('NON_NUMERIC','block','Non-finite or invalid numeric value',field))
    for field in ('revenue','total_assets','shares_diluted'):
        val=_number(snapshot.get(field))
        if val is not None and val<=0:
            issues.append(_issue('NON_POSITIVE','block' if field=='shares_diluted' else 'warning',
                                 'Value is non-positive; verify sign and units',field))
    assets=_number(snapshot.get('total_assets'))
    liabilities=_number(snapshot.get('total_liabilities'))
    equity=_number(snapshot.get('shareholders_equity'))
    if None not in (assets,liabilities,equity):
        delta=abs(assets-liabilities-equity)
        tolerance=max(Decimal('1'),abs(assets)*Decimal('0.01'))
        if delta>tolerance:
            issues.append(_issue('BALANCE_MISMATCH','block',
                                 'Assets != liabilities + equity (1% tolerance)','total_assets'))
    elif assets is not None and equity is not None:
        issues.append(_issue('BALANCE_INCOMPLETE','warning','Liabilities unavailable; balance cannot be reconciled','total_liabilities'))
    ocf=_number(snapshot.get('operating_cash_flow'))
    capex=_number(snapshot.get('capital_expenditure'))
    if ocf is not None and capex is not None and capex<0:
        issues.append(_issue('CAPEX_SIGN','warning','Capex is negative; confirm cash-flow sign convention','capital_expenditure'))
    status='blocked' if any(x['severity']=='block' for x in issues) else ('review' if issues else 'passed')
    return {'symbol':snapshot.get('symbol'),'period_end':snapshot.get('period_end'),
            'source':snapshot.get('source'),'status':status,'eligible_for_valuation':status!='blocked',
            'issues':issues,'policy':'Review warnings; passing checks does not validate economic accuracy.'}

def compare_sources(records: list[dict], field: str, *, tolerance_pct: float=2.0) -> dict:
    """Compare same-period, same-unit figures; never auto-convert FX or choose a winner."""
    if len(records)<2: return {'status':'insufficient_sources','issues':[]}
    keys=('symbol','period_end','period_type','currency','units')
    if any(any(rec.get(k)!=records[0].get(k) for k in keys) for rec in records[1:]):
        return {'status':'incomparable','issues':[_issue('DIFFERENT_BASIS','block','Period/currency/units/symbol mismatch')]}
    vals=[_number(rec.get(field)) for rec in records]
    if any(v is None for v in vals):
        return {'status':'incomparable','issues':[_issue('MISSING_COMPARISON_VALUE','warning',f'Missing {field}',field)]}
    lo,hi=min(vals),max(vals)
    denominator=max(abs(lo),abs(hi),Decimal('0.00000001'))
    gap=float((hi-lo)/denominator*100)
    return {'status':'conflict' if gap>tolerance_pct else 'consistent','field':field,
            'difference_pct':round(gap,4),'sources':[r.get('source') for r in records],
            'issues':[_issue('SOURCE_CONFLICT','warning','Values differ beyond tolerance',field)] if gap>tolerance_pct else []}
