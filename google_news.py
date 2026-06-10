"""Google News RSS fallback adapter.

Per-state instances cast a wide net for any news mentioning veterinary public
health topics in that state. Output is intentionally noisy — the LLM relevance
pass (in app.llm.processor) filters down to vet-actionable items.

Trust note: news articles are not primary sources. The frontend should display
these with a clear "news" tag and lower visual priority than state-ag or federal
adapters. The Alert.source_type="news" enables exactly that.

robots.txt: Google News RSS is publicly accessible without restriction.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from urllib.parse import quote

import feedparser
import httpx

from app.models import Alert
from app.sources.base import BaseAdapter

logger = logging.getLogger(__name__)


# Query intentionally veterinary-flavored. Tuned to catch outbreak/recall language
# without dragging in unrelated public health stories.
QUERY_TEMPLATE = (
    '("animal disease" OR "avian influenza" OR "HPAI" OR "screwworm" OR '
    '"pet food recall" OR "veterinary recall" OR "rabies" OR "anthrax" OR '
    '"chronic wasting disease" OR "EHV" OR "vesicular stomatitis") '
    '"{state_name}"'
)

STATE_NAMES = {
    "AZ": "Arizona", "CA": "California", "NM": "New Mexico",
    "NV": "Nevada", "TX": "Texas",
}


class GoogleNewsStateAdapter(BaseAdapter):
    """One instance per state. Use ``for_state()`` to construct."""

    source_type = "news"

    def __init__(self, state_code: str):
        if state_code not in STATE_NAMES:
            raise ValueError(f"Unsupported state {state_code}")
        self.state = state_code
        self.name = f"Google News ({state_code})"
        self.state_name = STATE_NAMES[state_code]

    @classmethod
    def for_state(cls, state_code: str) -> "GoogleNewsStateAdapter":
        return cls(state_code)

    async def fetch(self, client: httpx.AsyncClient, days: int) -> list[Alert]:
        query = QUERY_TEMPLATE.format(state_name=self.state_name)
        url = (
            f"https://news.google.com/rss/search?q={quote(query)}"
            f"&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            resp = await client.get(url, timeout=self.timeout, headers=self.headers)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Google News (%s) fetch failed: %s", self.state, e)
            return []

        feed = feedparser.parse(resp.text)
        if feed.bozo:
            logger.warning("Google News (%s) feed had parse issues: %s",
                           self.state, feed.bozo_exception)

        cutoff = date.today() - timedelta(days=days)
        alerts: list[Alert] = []
        for entry in feed.entries:
            # feedparser converts to a time.struct_time
            published_struct = getattr(entry, "published_parsed", None)
            if not published_struct:
                continue
            pub = date(published_struct.tm_year,
                      published_struct.tm_mon,
                      published_struct.tm_mday)
            if pub < cutoff:
                continue

            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            if not title or not link:
                continue

            # Google News titles look like "Real title - Source Name". Keep both.
            raw_text = " | ".join(filter(None, [
                title,
                entry.get("summary", "")[:500],
            ]))

            alerts.append(Alert(
                id=self.make_id(self.name, link),
                source=self.name,
                source_type="news",
                title=title,
                url=link,
                published=pub,
                state=self.state,
                category="other",  # LLM will refine
                raw_text=raw_text,
            ))
        logger.info("Google News (%s): %d alerts", self.state, len(alerts))
        return alerts
