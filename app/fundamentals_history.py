"""Versioned FY financial snapshots and conservative historical metrics.
No FX conversion, fiscal calendar harmonization, or vendor data acquisition.
"""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import FinancialSnapshot
from .fundamentals import Financials, calculate
from .sources import validate_source
from .data_quality import check_snapshot


def validate_history_snapshot(item: Financials):
    """Shared permission/quality boundary before history writes or metrics."""
    validate_source(item.source, automated=False)
    if item.units is not None and item.units != 'ones':
        raise ValueError('FINANCIAL_UNITS_REQUIRE_NORMALIZATION')
    data = item.model_dump(mode='json')
    report = check_snapshot(data)
    if report['status'] == 'blocked':
        codes = ','.join(sorted({issue['code'] for issue in report['issues']
                                 if issue['severity'] == 'block'}))
        raise ValueError('FINANCIAL_QUALITY_BLOCKED:' + codes)
    return data, report


def store_snapshot(db: Session, item: Financials) -> FinancialSnapshot:
    data, _ = validate_history_snapshot(item)
    period = date.fromisoformat(item.period_end)
    stmt = select(FinancialSnapshot).where(
        FinancialSnapshot.symbol == item.symbol.upper(),
        FinancialSnapshot.period_end == period,
        FinancialSnapshot.period_type == item.period_type,
        FinancialSnapshot.currency == item.currency,
        FinancialSnapshot.source == item.source)
    record = db.scalar(stmt)
    # JSON-mode validation data preserves Decimal text and explicit metadata.
    data['symbol'] = item.symbol.upper()
    if record is None:
        record = FinancialSnapshot(symbol=item.symbol.upper(), period_end=period,
                                   period_type=item.period_type, currency=item.currency,
                                   source=item.source, payload=data)
        db.add(record)
    else:
        record.payload = data
    db.flush()
    return record


def annual_cagr(start, end, years):
    if start is None or end is None or years <= 0:
        return None
    a, b = Decimal(str(start)), Decimal(str(end))
    if a <= 0 or b <= 0:
        return None
    return round(float(((b/a) ** (Decimal(1)/Decimal(str(years))) - 1)*100), 4)


def history_report(db: Session, symbol: str, currency: str, source: str, max_years: int = 10):
    validate_source(source, automated=False)
    records = db.scalars(select(FinancialSnapshot).where(
        FinancialSnapshot.symbol == symbol.upper(),
        FinancialSnapshot.currency == currency,
        FinancialSnapshot.source == source,
        FinancialSnapshot.period_type == 'FY').order_by(FinancialSnapshot.period_end)).all()
    # One FY record per calendar year. Multiple fiscal year-ends in a year are ambiguous.
    years = [r.period_end.year for r in records]
    if len(years) != len(set(years)):
        raise ValueError('Multiple fiscal year-end records in a calendar year; manual reconciliation required')
    records = records[-max_years:]
    entries = [Financials.model_validate(r.payload) for r in records]
    quality_reports = []
    for record, entry in zip(records, entries):
        if (entry.symbol.upper(), date.fromisoformat(entry.period_end), entry.period_type,
                entry.currency, entry.source) != (record.symbol, record.period_end,
                record.period_type, record.currency, record.source):
            raise ValueError('FINANCIAL_SNAPSHOT_IDENTITY_MISMATCH')
        _, quality = validate_history_snapshot(entry)
        quality_reports.append(quality)
    metrics = [calculate(f)['metrics'] for f in entries]
    warnings = ['Historical ROIC/ROE/ROA use ending balance sheet values, not average balances.',
                'Financial records must use consistent accounting basis, units, fiscal year-end, and currency.',
                'No inflation/FX/corporate-action adjustments; no point-in-time filing history.']
    warnings.extend(f"{report['period_end']}: {issue['code']} - {issue['message']}"
                    for report in quality_reports for issue in report['issues']
                    if issue['severity'] == 'warning')
    if len(entries) >= 2:
        gaps = [entries[i].period_end[:4] for i in range(1,len(entries))
                if int(entries[i].period_end[:4]) - int(entries[i-1].period_end[:4]) != 1]
        if gaps: warnings.append('Missing fiscal years or gaps in series; CAGR spans calendar years, not observed records.')
    trends = {}
    for field in ('revenue','net_income','operating_cash_flow'):
        trends[field+'_cagr_pct'] = annual_cagr(getattr(entries[0],field),getattr(entries[-1],field),
                                                  (date.fromisoformat(entries[-1].period_end)-date.fromisoformat(entries[0].period_end)).days/365.2425) if len(entries)>=2 else None
    for field in ('roic_pct','roe_pct','net_margin_pct','fcf_margin_pct'):
        series=[{'year':int(f.period_end[:4]),'value':m[field]} for f,m in zip(entries,metrics)]
        trends[field+'_history']=series
        values=[x['value'] for x in series if x['value'] is not None]
        trends[field+'_change_pp'] = round(values[-1]-values[0],4) if len(values)>=2 else None
    latest = entries[-1] if entries else None
    latest_metrics = metrics[-1] if metrics else None
    debt_to_equity = None
    if latest and latest.total_debt is not None and latest.shareholders_equity is not None and latest.shareholders_equity>0:
        debt_to_equity=round(float(latest.total_debt/latest.shareholders_equity),4)
    financial_health = {'debt_to_equity':debt_to_equity,
                        'net_debt':latest_metrics['net_debt'] if latest_metrics else None,
                        'latest_fcf':latest_metrics['free_cash_flow'] if latest_metrics else None,
                        'latest_fcf_positive':(latest_metrics['free_cash_flow']>0) if latest_metrics and latest_metrics['free_cash_flow'] is not None else None}
    return {'symbol':symbol.upper(),'currency':currency,'source':source,
            'units':'ones' if entries else None,
            'years':[f.period_end for f in entries],'records':len(entries),
            'trends':trends,'financial_health':financial_health,
            'warnings':warnings,'assessment':'DESCRIPTIVE_ONLY_NOT_INVESTMENT_ADVICE'}
