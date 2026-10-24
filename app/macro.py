"""Deterministic macro surprise triage. No forecasts or automatic trading."""
from datetime import datetime, timezone
from math import isfinite
from typing import Literal
from pydantic import BaseModel, Field, model_validator

DIRECTION = {"CPI_YOY":-1, "CORE_CPI_YOY":-1, "PCE_CORE_YOY":-1,
             "UNEMPLOYMENT_RATE":-1, "NONFARM_PAYROLLS":1, "GDP_QOQ":1,
             "FED_RATE":-1, "RETAIL_SALES":1}
IMPACT = {"CPI_YOY":5,"CORE_CPI_YOY":5,"PCE_CORE_YOY":5,
          "UNEMPLOYMENT_RATE":4,"NONFARM_PAYROLLS":4,"GDP_QOQ":3,
          "FED_RATE":5,"RETAIL_SALES":2}

class Event(BaseModel):
    event_id: str = Field(min_length=1)
    indicator: str
    country: str = Field(min_length=2)
    released_at: datetime
    actual: float | None = None
    consensus: float | None = None
    previous: float | None = None
    historical_surprise_std: float | None = Field(default=None, gt=0)
    unit: str = Field(min_length=1)
    source_url: str = Field(min_length=8)
    consensus_asof: datetime | None = None
    category: str = "macro"

    @model_validator(mode="after")
    def validate_data(self):
        for v in (self.actual,self.consensus,self.previous):
            if v is not None and not isfinite(v): raise ValueError("nonfinite data")
        if self.released_at.tzinfo is None: raise ValueError("released_at needs timezone")
        if self.consensus_asof is not None:
            if self.consensus_asof.tzinfo is None: raise ValueError("consensus_asof needs timezone")
            if self.consensus_asof > self.released_at: raise ValueError("consensus must predate release")
        if not self.source_url.startswith(("https://","http://")):
            raise ValueError("source_url must be HTTP(S)")
        return self

def evaluate(events: list[Event], asof: datetime | None = None) -> dict:
    asof=asof or datetime.now(timezone.utc)
    if asof.tzinfo is None: raise ValueError("asof must be timezone-aware")
    unique={}
    for event in events:
        if event.event_id in unique:
            raise ValueError(f"duplicate event_id: {event.event_id}; reconcile revisions upstream")
        unique[event.event_id]=event
    output=[]
    for e in unique.values():
        if e.released_at > asof:
            status="upcoming"; surprise=None; standardized=None; priority=None
        elif e.actual is None or e.consensus is None:
            status="missing_actual_or_consensus"; surprise=None; standardized=None; priority=None
        else:
            status="released"; surprise=round(e.actual-e.consensus,6)
            standardized=round(surprise/e.historical_surprise_std,4) if e.historical_surprise_std else None
            # Ranking requires calibrated historical dispersion. Do not fabricate a surprise score.
            priority=min(100,round(IMPACT.get(e.indicator,1)*min(abs(standardized),4)*5)) if standardized is not None else None
        direction=DIRECTION.get(e.indicator)
        output.append({"event_id":e.event_id,"indicator":e.indicator,"country":e.country,
            "released_at":e.released_at.isoformat(),"status":status,"actual":e.actual if status=="released" else None,
            "consensus":e.consensus,"unit":e.unit,"surprise":surprise,
            "standardized_surprise":standardized,"priority_score":priority,
            "simple_directional_hint":("favorable" if surprise*direction>0 else "unfavorable" if surprise*direction<0 else "neutral") if surprise is not None and direction else "undetermined",
            "source_url":e.source_url,"limitations":["Single-release heuristic; policy expectations, revisions, market pricing and cross-asset reactions are not included"]})
    output.sort(key=lambda r:(r['priority_score'] is None,-(r['priority_score'] or 0),r['released_at']))
    return {"asof":asof.isoformat(),"events":output,"overall_market_call":"NOT_AVAILABLE",
            "note":"No aggregate directional forecast until expectation probabilities, market reactions and cross-event dependencies are integrated."}
