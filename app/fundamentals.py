"""Financial ratios for annual/TTM inputs, not investment recommendations."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class Financials(BaseModel):
    symbol: str = Field(pattern=r'^[A-Za-z0-9._-]{1,32}$')
    period_end: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    period_type: Literal['FY','TTM']
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    source: str = 'manual'
    revenue: Decimal | None = None
    net_income: Decimal | None = None
    operating_income: Decimal | None = None
    income_tax: Decimal | None = None
    pretax_income: Decimal | None = None
    total_assets: Decimal | None = None
    shareholders_equity: Decimal | None = None
    total_debt: Decimal | None = None
    cash: Decimal | None = None
    operating_cash_flow: Decimal | None = None
    capital_expenditure: Decimal | None = None  # Positive magnitude, not cash-flow statement signed amount
    invested_capital: Decimal | None = None
    shares_diluted: Decimal | None = None
    share_price: Decimal | None = None
    dividends_per_share: Decimal | None = None
    asof_price_date: str | None = None

    @model_validator(mode='after')
    def validate_inputs(self):
        from datetime import date
        date.fromisoformat(self.period_end)
        if self.asof_price_date: date.fromisoformat(self.asof_price_date)
        for k in ('revenue','total_assets','total_debt','cash','capital_expenditure','invested_capital','shares_diluted','share_price','dividends_per_share'):
            v=getattr(self,k)
            if v is not None and v < 0: raise ValueError(f'{k} cannot be negative')
        if self.shares_diluted == 0: raise ValueError('shares_diluted must be positive')
        return self

def ratio(a, b, percent=False):
    if a is None or b is None or b <= 0: return None
    val = Decimal(a)/Decimal(b)
    return round(float(val * (100 if percent else 1)), 4)

def calculate(f: Financials):
    d=f.model_dump()
    ocf=f.operating_cash_flow
    capex=f.capital_expenditure
    fcf=(ocf-capex) if ocf is not None and capex is not None else None
    market_cap=(f.share_price*f.shares_diluted) if f.share_price is not None and f.shares_diluted is not None else None
    net_debt=(f.total_debt-f.cash) if f.total_debt is not None and f.cash is not None else None
    ev=(market_cap+net_debt) if market_cap is not None and net_debt is not None else None
    effective_tax=ratio(f.income_tax,f.pretax_income)
    nopat=f.operating_income*(1-Decimal(str(effective_tax))) if f.operating_income is not None and effective_tax is not None and 0<=effective_tax<=1 else None
    result={
        'net_margin_pct':ratio(f.net_income,f.revenue,True),
        'operating_margin_pct':ratio(f.operating_income,f.revenue,True),
        'roe_pct':ratio(f.net_income,f.shareholders_equity,True),
        'roa_pct':ratio(f.net_income,f.total_assets,True),
        'roic_pct':ratio(nopat,f.invested_capital,True),
        'free_cash_flow':float(fcf) if fcf is not None else None,
        'fcf_margin_pct':ratio(fcf,f.revenue,True),
        'net_debt':float(net_debt) if net_debt is not None else None,
        'market_cap':float(market_cap) if market_cap is not None else None,
        'enterprise_value':float(ev) if ev is not None else None,
        'pe':ratio(market_cap,f.net_income),
        'price_to_sales':ratio(market_cap,f.revenue),
        'fcf_yield_pct':ratio(fcf,market_cap,True),
        'dividend_yield_pct':ratio(f.dividends_per_share,f.share_price,True),
    }
    return {'symbol':f.symbol,'period_end':f.period_end,'period_type':f.period_type,'currency':f.currency,
            'source':f.source,'price_asof':f.asof_price_date,'metrics':result,
            'warnings':['Single-period ROE/ROA/ROIC use ending balances; prefer average capital balances.',
                        'FCF assumes capital_expenditure is a positive cash outflow magnitude.',
                        'Market ratios combine the specified share price with period financials; check date alignment.',
                        'No FX conversion, share-class reconciliation, adjustments, forecast or investment advice.']}
