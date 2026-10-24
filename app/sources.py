"""Policy-aware source registry. Registration never initiates network access."""
from dataclasses import dataclass, asdict
from typing import Literal

Access = Literal['official_api','licensed_api','manual_import','reference_only','disabled']

@dataclass(frozen=True)
class Source:
    key: str
    name: str
    access: Access
    permission_verified: bool
    enabled: bool
    notes: str

    def can_automate(self) -> bool:
        return self.enabled and self.permission_verified and self.access in ('official_api','licensed_api')

SOURCES = {
    s.key: s for s in [
        Source('ibkr','Interactive Brokers','licensed_api',False,False,'Activate after checking account entitlements, API and market-data license.'),
        Source('sec_edgar','SEC EDGAR','official_api',True,False,'Official US filings; implement SEC fair-access requirements, User-Agent and rate limits before enabling.'),
        Source('investolens','Investolens','reference_only',False,False,'No automated collection; obtain written permission and an authorized integration first.'),
        Source('investing_com','Investing.com','reference_only',False,False,'No scraping; verify licensing/API before integration.'),
        Source('finviz','Finviz','reference_only',False,False,'No scraping; verify licensing/API before integration.'),
        Source('manual','User-provided financial statement data','manual_import',True,True,'Only user-supplied data with appropriate usage rights; provenance required.'),
    ]
}

def list_sources():
    return [{**asdict(s),'automation_allowed':s.can_automate()} for s in SOURCES.values()]

def validate_source(key: str, automated: bool = False):
    if key not in SOURCES:
        raise ValueError('Unknown source; register and review permissions first')
    source = SOURCES[key]
    if automated and not source.can_automate():
        raise PermissionError('Automated access not authorized for this source')
    if not automated and source.access != 'manual_import':
        raise PermissionError('Only approved manual imports are accepted by this endpoint')
    return source
