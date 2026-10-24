"""SEC EDGAR read-only Company Facts client."""

import re
import time
import httpx

from .sources import validate_source


class SECEdgarClient:
    def __init__(self, user_agent: str):
        if not user_agent or not re.search(
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            user_agent
        ):
            raise ValueError(
                "SEC User-Agent must contain a contact email"
            )

        self.user_agent = user_agent
        self.last_request = 0.0

    def company_facts(self, cik: int) -> dict:
        validate_source("sec_edgar", automated=True)

        if not isinstance(cik, int) or isinstance(cik, bool):
            raise ValueError("CIK must be an integer")

        if not 1 <= cik <= 9999999999:
            raise ValueError("Invalid CIK")

        elapsed = time.monotonic() - self.last_request
        if elapsed < 0.25:
            time.sleep(0.25 - elapsed)

        url = (
            "https://data.sec.gov/api/xbrl/companyfacts/"
            f"CIK{cik:010d}.json"
        )

        self.last_request = time.monotonic()

        with httpx.Client(
            timeout=20,
            follow_redirects=False,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Invalid SEC response")

        if "facts" not in data or "cik" not in data:
            raise ValueError("Missing SEC Company Facts fields")

        if data["cik"] != cik:
            raise ValueError("SEC CIK mismatch")

        return data
