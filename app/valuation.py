"""Explicit-assumption FCFF DCF and terminal multiple scenario analysis.

No live market data, investment advice, or order execution.
"""
from math import isfinite
from pydantic import BaseModel, Field, model_validator

class Scenario(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    growth_rate: float = Field(ge=-0.90, le=1.0)
    discount_rate: float = Field(gt=0, le=1.0)
    terminal_growth_rate: float = Field(ge=-0.10, le=0.15)
    years: int = Field(default=5, ge=1, le=20)
    terminal_multiple: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode='after')
    def check(self):
        if self.terminal_multiple is None and self.discount_rate <= self.terminal_growth_rate:
            raise ValueError('discount_rate must exceed terminal_growth_rate for perpetuity valuation')
        return self

class ValuationRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    currency: str = Field(default='USD', min_length=3, max_length=3)
    base_fcff: float = Field(gt=0, description='Normalized annual unlevered free cash flow')
    net_debt: float = Field(description='Total debt minus cash; negative is net cash')
    diluted_shares: float = Field(gt=0)
    current_price: float = Field(gt=0, description='Explicit price input, not a fetched quote')
    price_asof: str = Field(min_length=10, max_length=30)
    scenarios: list[Scenario] = Field(min_length=1, max_length=10)
    sensitivity_growth_steps: list[float] = Field(default_factory=lambda: [-0.01, 0, 0.01], min_length=1, max_length=9)
    sensitivity_discount_steps: list[float] = Field(default_factory=lambda: [-0.01, 0, 0.01], min_length=1, max_length=9)

    @model_validator(mode='after')
    def check(self):
        names=[s.name for s in self.scenarios]
        if len(names)!=len(set(names)):
            raise ValueError('scenario names must be unique')
        return self

def _dcf(req: ValuationRequest, scenario: Scenario) -> dict:
    cashflows=[]
    pv=0.0
    for yr in range(1,scenario.years+1):
        fcff=req.base_fcff*(1+scenario.growth_rate)**yr
        discounted=fcff/(1+scenario.discount_rate)**yr
        cashflows.append({'year':yr,'fcff':round(fcff,2),'present_value':round(discounted,2)})
        pv+=discounted
    final= req.base_fcff*(1+scenario.growth_rate)**scenario.years
    if scenario.terminal_multiple is not None:
        terminal=final*scenario.terminal_multiple
        terminal_method='EXIT_FCFF_MULTIPLE'
    else:
        terminal=final*(1+scenario.terminal_growth_rate)/(scenario.discount_rate-scenario.terminal_growth_rate)
        terminal_method='GORDON_GROWTH'
    terminal_pv=terminal/(1+scenario.discount_rate)**scenario.years
    enterprise=pv+terminal_pv
    equity=enterprise-req.net_debt
    fair=equity/req.diluted_shares
    if not all(isfinite(v) for v in [enterprise,equity,fair,terminal_pv]):
        raise ValueError('non-finite valuation')
    # Negative equity values are reported, not floored; IRR is undefined for negative exit values.
    implied_cagr=(fair/req.current_price)**(1/scenario.years)-1 if fair>0 else None
    return {
        'scenario':scenario.name,'assumptions':scenario.model_dump(),
        'forecast_cashflows':cashflows,'terminal_method':terminal_method,
        'pv_forecast_fcff':round(pv,2),'pv_terminal_value':round(terminal_pv,2),
        'terminal_value_share_of_enterprise_pct':round(100*terminal_pv/enterprise,2) if enterprise else None,
        'enterprise_value':round(enterprise,2),'equity_value':round(equity,2),
        'fair_value_per_share':round(fair,4),
        'upside_pct':round(100*(fair/req.current_price-1),2),
        'margin_of_safety_pct':round(100*(1-req.current_price/fair),2) if fair>0 else None,
        'implied_annual_price_cagr_pct':round(100*implied_cagr,2) if implied_cagr is not None else None,
    }

def evaluate(req: ValuationRequest) -> dict:
    results=[_dcf(req,s) for s in req.scenarios]
    base=next((s for s in req.scenarios if s.name.lower()=='base'),req.scenarios[0])
    sensitivity=[]
    for delta_discount in req.sensitivity_discount_steps:
        row=[]
        for delta_growth in req.sensitivity_growth_steps:
            candidate=base.model_copy(update={
                'discount_rate':base.discount_rate+delta_discount,
                'growth_rate':base.growth_rate+delta_growth,
            })
            try:
                candidate=Scenario.model_validate(candidate.model_dump())
                val=_dcf(req,candidate)['fair_value_per_share']
            except (ValueError,OverflowError):
                val=None
            row.append({'growth_rate':round(candidate.growth_rate,5),'fair_value_per_share':val})
        sensitivity.append({'discount_rate':round(base.discount_rate+delta_discount,5),'values':row})
    return {'symbol':req.symbol,'currency':req.currency,'current_price':req.current_price,
            'price_asof':req.price_asof,'valuation_method':'FCFF_DCF',
            'scenarios':results,'sensitivity_base_scenario':base.name,
            'sensitivity':sensitivity,'data_mode':'EXPLICIT_INPUT_ONLY',
            'cautions':['Projected FCFF growth is an assumption, not a forecast verified against market data.',
                        'Annualized return is a price-only implied CAGR, excludes dividends, taxes, FX and execution costs.',
                        'FCFF must be normalized and unlevered; net debt and diluted shares must match the same valuation date.',
                        'Terminal value can dominate DCF; inspect terminal_value_share_of_enterprise_pct.']}
