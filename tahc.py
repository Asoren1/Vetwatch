"""Texas Animal Health Commission news scraper.

Source: https://www.tahc.texas.gov/news/

Structure observed (2026-06):
- Page contains H2 headings per year ("2026", "2025", ...) followed by a markdown
  table with two columns: "Month Day, Year" and "[Title](pdf_url)".
- PDFs live at /news/YYYY/YYYY-MM-DD_TopicName.pdf.
- Titles almost always include the affected county directly, e.g.
  "Anthrax Confirmed in a Briscoe County Steer".

We extract: date (from the cell text), title (link text), URL (link href),
county (regex on title), category (heuristic on title), and use the title as
raw_text for downstream LLM summarization.

If the page structure changes, the scraper logs a warning and returns []
rather than crashing.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from app.models import Alert
from app.sources.base import BaseAdapter

logger = logging.getLogger(__name__)


# Common Texas county names that show up in TAHC titles, used to extract county
# without an LLM call. Not exhaustive — anything missed falls through to the LLM.
COUNTY_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+County\b")

# Heuristics for category. Order matters — first match wins.
# Stems use \w* to match inflected forms (Confirmed, Proposals, Detected, Adopted, etc.)
CATEGORY_PATTERNS = [
    (re.compile(r"\b(rule\w*|adopt\w*|propos\w*|public comment|order|edo|executive director order)\b", re.I), "regulatory"),
    (re.compile(r"\b(detect\w*|confirm\w*|positive|outbreak\w*|case\w*)\b", re.I), "outbreak"),
    (re.compile(r"\b(reminder\w*|biosecur\w*|requirement\w*|advisor\w*)\b", re.I), "advisory"),
    (re.compile(r"\brecall\w*\b", re.I), "recall"),
]


def _categorize(title: str) -> str:
    for pat, cat in CATEGORY_PATTERNS:
        if pat.search(title):
            return cat
    return "other"


def _extract_county(title: str) -> str | None:
    m = COUNTY_PATTERN.search(title)
    if not m:
        return None
    candidate = m.group(1)
    # Filter out false positives — words that look like counties but aren't
    # ("Public County" would never appear; this is just a guard for obvious noise).
    if candidate.lower() in {"the", "this", "that"}:
        return None
    return candidate


def _parse_date_cell(text: str) -> date | None:
    """Parse strings like 'June 5, 2026' or '06/09'."""
    text = text.strip()
    # Full format: "June 5, 2026"
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


class TAHCAdapter(BaseAdapter):
    name = "TAHC"
    source_type = "state-ag"
    state = "TX"

    endpoint = "https://www.tahc.texas.gov/news/"

    async def fetch(self, client: httpx.AsyncClient, days: int) -> list[Alert]:
        cutoff = date.today() - timedelta(days=days)
        try:
            resp = await client.get(self.endpoint, timeout=self.timeout, headers=self.headers)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("TAHC fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # The news page renders as tables, one per year. Each row is:
        #   <td>Month Day, Year</td><td><a href="...pdf">Title</a></td>
        # We scan every table row anywhere in the page and try to parse it.
        alerts: list[Alert] = []
        rows_seen = 0
        rows_parsed = 0

        for row in soup.find_all("tr"):
            rows_seen += 1
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            pub = _parse_date_cell(cells[0].get_text(strip=True))
            if not pub:
                continue
            if pub < cutoff:
                # Tables are in reverse chronological order within a year, but
                # we don't break — just skip, in case ordering is inconsistent.
                continue
            link = cells[1].find("a")
            if not link or not link.get("href"):
                continue
            title = link.get_text(strip=True)
            url = link["href"]
            if not url.startswith("http"):
                url = "https://www.tahc.texas.gov" + url

            rows_parsed += 1
            alerts.append(Alert(
                id=self.make_id(self.name, url),
                source=self.name,
                source_type="state-ag",
                title=title,
                url=url,
                published=pub,
                state="TX",
                county=_extract_county(title),
                category=_categorize(title),
                raw_text=title,  # PDF body would be richer but requires per-record fetch
            ))

        if rows_seen > 0 and rows_parsed == 0:
            logger.warning(
                "TAHC scraper saw %d rows but parsed 0 — HTML structure may have changed",
                rows_seen,
            )
        logger.info("TAHC: parsed %d alerts within %d days", len(alerts), days)
        return alerts
