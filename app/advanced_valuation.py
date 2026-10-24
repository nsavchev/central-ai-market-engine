"""Auditable two-stage FCFF DCF with scenario weights and reverse DCF.
Inputs are explicit, not live market data. Values and shares must use consistent units.
"""
from math import isfinite
from pydantic import BaseModel, Field, model_validator

class Case(BaseModel):
    name: str = Field(min_length=1)
    probability: float = Field(ge=0, le=1)
    growth_first_five: float = Field(ge=-0.8, le=1)
    growth_next_five: float = Field(ge=-0.8, le=1)
    discount_rate: float = Field(gt=0, le=1)
    terminal_growth: float = Field(ge=-0.1, le=0.15)
    @model_validator(mode="after")
    def validate_spread(self):
        if self.discount_rate <= self.terminal_growth:
            raise ValueError("discount_rate must exceed terminal_growth")
        return self

class AdvancedRequest(BaseModel):
    symbol: str = Field(min_length=1)
    currency: str = Field(default="USD",min_length=3,max_length=3)
    normalized_fcff: float = Field(gt=0)
    net_debt: float
    diluted_shares: float = Field(gt=0)
    price: float = Field(gt=0)
    price_asof: str = Field(min_length=10)
    safety_buffer: float = Field(default=.25,ge=0,lt=1)
    cases: list[Case] = Field(min_length=3,max_length=10)
    @model_validator(mode="after")
    def validate_cases(self):
        if abs(sum(c.probability for c in self.cases)-1)>1e-8:
            raise ValueError("scenario probabilities must sum to 1")
        if len({c.name.lower() for c in self.cases})!=len(self.cases):
            raise ValueError("scenario names must be unique")
        return self

def value(req: AdvancedRequest, case: Case, growth_override: float | None = None) -> dict:
    fcff=req.normalized_fcff
    pv=0.
    flows=[]
    for year in range(1,11):
        g=(growth_override if growth_override is not None else case.growth_first_five) if year<=5 else case.growth_next_five
        fcff*=1+g
        disc=fcff/(1+case.discount_rate)**year
        pv+=disc
        flows.append({"year":year,"fcff":round(fcff,2),"present_value":round(disc,2)})
    terminal=fcff*(1+case.terminal_growth)/(case.discount_rate-case.terminal_growth)
    pv_terminal=terminal/(1+case.discount_rate)**10
    ev=pv+pv_terminal
    fair=(ev-req.net_debt)/req.diluted_shares
    if not all(isfinite(x) for x in (pv,ev,fair,pv_terminal)):
        raise ValueError("nonfinite valuation")
    return {"name":case.name,"probability":case.probability,"fair_value":round(fair,4),
            "upside_pct":round(100*(fair/req.price-1),2),"buy_below":round(max(0,fair)*(1-req.safety_buffer),4),
            "terminal_share_pct":round(100*pv_terminal/ev,2),"fcff_projection":flows,
            "pv_explicit_fcff":round(pv,2),"pv_terminal":round(pv_terminal,2),
            "enterprise_value":round(ev,2),"equity_value":round(ev-req.net_debt,2)}

def reverse_growth(req: AdvancedRequest, case: Case) -> dict:
    # Solve the first-five-year growth required to justify price, holding all other assumptions fixed.
    # Root is searched in [-80%, 100%]; outside range is explicitly reported, not extrapolated.
    lo,hi=-.8,1.
    target=req.price
    f_lo=value(req,case,lo)["fair_value"]-target
    f_hi=value(req,case,hi)["fair_value"]-target
    if f_lo>0: return {"status":"BELOW_RANGE","required_growth":None}
    if f_hi<0: return {"status":"ABOVE_RANGE","required_growth":None}
    for _ in range(70):
        mid=(lo+hi)/2
        v=value(req,case,mid)["fair_value"]
        if v<target: lo=mid
        else: hi=mid
    return {"status":"SOLVED","required_growth":round((lo+hi)/2,6)}

def analyze(req: AdvancedRequest) -> dict:
    results=[value(req,c) for c in req.cases]
    weighted=sum(c.probability*v["fair_value"] for c,v in zip(req.cases,results))
    base=next((c for c in req.cases if c.name.lower() in ("base","базов")),req.cases[0])
    alerts=[]
    if max(v["terminal_share_pct"] for v in results)>80: alerts.append("Terminal value exceeds 80% in at least one case")
    if any(v["equity_value"]<=0 for v in results): alerts.append("At least one scenario has non-positive equity value")
    return {"symbol":req.symbol,"currency":req.currency,"price":req.price,"price_asof":req.price_asof,
            "method":"TWO_STAGE_FCFF_DCF_10Y","cases":results,
            "probability_weighted_fair_value":round(weighted,4),
            "probability_weighted_upside_pct":round(100*(weighted/req.price-1),2),
            "weighted_buy_below":round(max(0,weighted)*(1-req.safety_buffer),4),
            "reverse_dcf_base_case":reverse_growth(req,base),"alerts":alerts,
            "source_mode":"EXPLICIT_INPUT_ONLY",
            "limitations":["Probabilities are subjective scenario weights, not statistically calibrated odds.",
            "Reverse DCF varies only first-five-year growth; other assumptions stay fixed.",
            "FCFF must be unlevered and normalized; net debt and diluted shares must use the same units and date.",
            "No dividend, tax, FX, buyback, dilution or execution-cost forecast; fair value is not a guaranteed future price."]}
