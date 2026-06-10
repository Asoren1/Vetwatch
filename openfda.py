"""openFDA food + drug enforcement adapter.

Docs:
  https://open.fda.gov/apis/food/enforcement/
  https://open.fda.gov/apis/drug/enforcement/

We pull both endpoints and filter to vet-relevant items downstream via the LLM.
The food enforcement API returns pet food recalls under the same endpoint as
human food — they're distinguished only by product_description text.

The report_date field is a yyyymmdd string. distribution_pattern is a free-text
field like "Texas, Arizona, California" or "nationwide".

Failure modes handled:
- Network errors → empty list, log warning
- Schema drift → skip that record, keep going
- Date parse errors → skip that record
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import httpx

from app.models import Alert
from app.sources.base import BaseAdapter

logger = logging.getLogger(__name__)

# Two-letter state code → full name (for matching distribution_pattern strings)
STATE_NAMES = {
    "AZ": "Arizona", "CA": "California", "NM": "New Mexico",
    "NV": "Nevada", "TX": "Texas",
}


def _parse_fda_date(s: str) -> Optional[date]:
    """openFDA dates are 'YYYYMMDD' strings. Return None on bad input."""
    if not s or len(s) != 8:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def _states_from_distribution(pattern: str) -> list[str]:
    """Best-effort extraction of state codes from a free-text distribution_pattern.

    Examples we handle:
      'nationwide' → []  (means national, no specific state)
      'Texas and Arizona' → ['TX', 'AZ']
      'TX, AZ, CA' → ['TX', 'AZ', 'CA']
    """
    if not pattern:
        return []
    pattern_lower = pattern.lower()
    if "nationwide" in pattern_lower or "national" in pattern_lower:
        return []
    found = []
    for code, name in STATE_NAMES.items():
        if name.lower() in pattern_lower or f" {code.lower()}" in f" {pattern_lower}":
            found.append(code)
    return found


class OpenFDAFoodEnforcementAdapter(BaseAdapter):
    name = "FDA Food Recalls"
    source_type = "federal"
    state = None

    endpoint = "https://api.fda.gov/food/enforcement.json"

    async def fetch(self, client: httpx.AsyncClient, days: int) -> list[Alert]:
        cutoff = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
        today = date.today().strftime("%Y%m%d")
        params = {
            "search": f"report_date:[{cutoff}+TO+{today}]",
            "limit": 100,
        }
        try:
            resp = await client.get(self.endpoint, params=params,
                                    timeout=self.timeout, headers=self.headers)
            if resp.status_code == 404:
                # openFDA returns 404 when no records match — not an error
                return []
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("OpenFDA food fetch failed: %s", e)
            return []
        except ValueError as e:
            logger.warning("OpenFDA food returned non-JSON: %s", e)
            return []

        alerts: list[Alert] = []
        for rec in data.get("results", []):
            pub = _parse_fda_date(rec.get("report_date", ""))
            if pub is None:
                continue

            # Build a synthetic URL — openFDA doesn't link to a press release per record.
            # Use the recall_number as the identifier in a search-style URL.
            recall_no = rec.get("recall_number", "")
            url = (
                f"https://www.accessdata.fda.gov/scripts/ires/index.cfm?Product={recall_no}"
                if recall_no else "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts"
            )

            title = (
                f"{rec.get('recalling_firm', 'Unknown firm')}: "
                f"{rec.get('product_description', 'product')[:120]}"
            )

            raw_text = " | ".join(filter(None, [
                rec.get("product_description"),
                rec.get("reason_for_recall"),
                f"Classification: {rec.get('classification', '')}",
                f"Distribution: {rec.get('distribution_pattern', '')}",
                f"Status: {rec.get('status', '')}",
            ]))

            states = _states_from_distribution(rec.get("distribution_pattern", ""))
            # If a recall hits multiple of our states, emit one alert each (lets per-state
            # filtering work cleanly). If none of our states match, emit one with state=None.
            if not states:
                alerts.append(Alert(
                    id=self.make_id(self.name, url + (recall_no or pub.isoformat())),
                    source=self.name,
                    source_type="federal",
                    title=title,
                    url=url,
                    published=pub,
                    state=None,
                    category="recall",
                    raw_text=raw_text,
                ))
            else:
                for st in states:
                    alerts.append(Alert(
                        id=self.make_id(self.name, f"{url}|{st}|{recall_no}"),
                        source=self.name,
                        source_type="federal",
                        title=title,
                        url=url,
                        published=pub,
                        state=st,
                        category="recall",
                        raw_text=raw_text,
                    ))
        return alerts


class OpenFDADrugEnforcementAdapter(BaseAdapter):
    """Same shape as food enforcement, different endpoint. Catches veterinary drug recalls."""
    name = "FDA Drug Recalls"
    source_type = "federal"
    state = None

    endpoint = "https://api.fda.gov/drug/enforcement.json"

    async def fetch(self, client: httpx.AsyncClient, days: int) -> list[Alert]:
        cutoff = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
        today = date.today().strftime("%Y%m%d")
        params = {
            "search": f"report_date:[{cutoff}+TO+{today}]",
            "limit": 100,
        }
        try:
            resp = await client.get(self.endpoint, params=params,
                                    timeout=self.timeout, headers=self.headers)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("OpenFDA drug fetch failed: %s", e)
            return []
        except ValueError as e:
            logger.warning("OpenFDA drug returned non-JSON: %s", e)
            return []

        alerts: list[Alert] = []
        for rec in data.get("results", []):
            pub = _parse_fda_date(rec.get("report_date", ""))
            if pub is None:
                continue

            recall_no = rec.get("recall_number", "")
            url = (
                f"https://www.accessdata.fda.gov/scripts/ires/index.cfm?Product={recall_no}"
                if recall_no else "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts"
            )

            title = (
                f"{rec.get('recalling_firm', 'Unknown firm')}: "
                f"{rec.get('product_description', 'product')[:120]}"
            )

            raw_text = " | ".join(filter(None, [
                rec.get("product_description"),
                rec.get("reason_for_recall"),
                f"Classification: {rec.get('classification', '')}",
                f"Distribution: {rec.get('distribution_pattern', '')}",
            ]))

            states = _states_from_distribution(rec.get("distribution_pattern", ""))
            if not states:
                alerts.append(Alert(
                    id=self.make_id(self.name, url + (recall_no or pub.isoformat())),
                    source=self.name,
                    source_type="federal",
                    title=title,
                    url=url,
                    published=pub,
                    state=None,
                    category="recall",
                    raw_text=raw_text,
                ))
            else:
                for st in states:
                    alerts.append(Alert(
                        id=self.make_id(self.name, f"{url}|{st}|{recall_no}"),
                        source=self.name,
                        source_type="federal",
                        title=title,
                        url=url,
                        published=pub,
                        state=st,
                        category="recall",
                        raw_text=raw_text,
                    ))
        return alerts
