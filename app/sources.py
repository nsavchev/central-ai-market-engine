"""Policy-aware source registry. Registration never initiates network access."""
from dataclasses import dataclass, asdict, replace
import os
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
        Source('manual','User-provided market and financial data','manual_import',True,True,'Only user-supplied data with appropriate usage rights; provenance required.'),
        Source('twelve_data','Twelve Data daily prices','official_api',False,False,'Private personal analysis only; explicit runtime enablement and usage-rights confirmation required. No redistribution.'),
    ]
}

def _configured_source(key):
    source = SOURCES[key]
    if key == 'twelve_data':
        source = replace(source,
            enabled=os.environ.get('MARKET_TWELVE_DATA_ENABLED') == '1',
            permission_verified=os.environ.get('MARKET_TWELVE_DATA_PRIVATE_USE_CONFIRMED') == '1')
    return source


def list_sources():
    sources = [_configured_source(key) for key in SOURCES]
    return [{**asdict(s),'automation_allowed':s.can_automate()} for s in sources]

def validate_source(key: str, automated: bool = False):
    if key not in SOURCES:
        raise ValueError('Unknown source; register and review permissions first')
    source = _configured_source(key)
    if automated and not source.can_automate():
        raise PermissionError('Automated access not authorized for this source')
    if not automated and (source.access != 'manual_import' or not source.enabled or not source.permission_verified):
        raise PermissionError('Only approved manual imports are accepted by this endpoint')
    return source
