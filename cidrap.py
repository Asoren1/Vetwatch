"""CIDRAP (Center for Infectious Disease Research and Policy) adapter.

University of Minnesota project; aggregates and reports on infectious disease
news daily. Excellent secondary source for federal data (APHIS HPAI, NWS, etc.)
when the primary sources are scrape-blocked.

Content quality is high: each article cites primary sources and includes
specific case counts, locations, and species. Lag from federal announcements
is typically <72 hours.

Feed mechanics:
  CIDRAP exposes topical RSS feeds. The catalog is at
  https://www.cidrap.umn.edu/rss-feeds. We default to the avian influenza
  feed since HPAI is the highest-priority vet topic right now, but the class
  takes a topic_slug so you can instantiate multiple (one per disease topic).

Two important caveats:
1. Feed URL pattern is the best-guess for Drupal sites. If the default URL
   404s, check https://www.cidrap.umn.edu/rss-feeds for the canonical list
   and update CIDRAP_FEEDS below.
2. CIDRAP coverage is national — not state-tagged. We set state=None and
   let the LLM extract state/county from the article body. This means
   CIDRAP items show up regardless of state filter (which is correct —
   a national outbreak summary IS relevant to any state's vets).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import feedparser
import httpx

from app.models import Alert
from app.sources.base import BaseAdapter

logger = logging.getLogger(__name__)


# Topic slug → human-readable name. Add more as needed.
# If a feed URL 404s, check https://www.cidrap.umn.edu/rss-feeds for the actual URL.
CIDRAP_FEEDS = {
    "avian-influenza-bird-flu": "Avian Influenza",
    "chronic-wasting-disease": "Chronic Wasting Disease",
    "antimicrobial-stewardship-resistance": "Antimicrobial Resistance",
    "foodborne-disease": "Foodborne Disease",
}


class CIDRAPAdapter(BaseAdapter):
    """One instance per topic feed. Use ``for_topic()`` to construct."""

    source_type = "news"  # CIDRAP is journalism + aggregation, not primary
    state = None  # National coverage; LLM extracts state/county per article

    def __init__(self, topic_slug: str):
        if topic_slug not in CIDRAP_FEEDS:
            raise ValueError(f"Unknown CIDRAP topic: {topic_slug}")
        self.topic_slug = topic_slug
        self.topic_name = CIDRAP_FEEDS[topic_slug]
        self.name = f"CIDRAP ({self.topic_name})"
        # Best-guess feed URL based on standard Drupal pattern.
        # If this 404s in practice, replace with the actual feed URL from
        # https://www.cidrap.umn.edu/rss-feeds.
        self.feed_url = f"https://www.cidrap.umn.edu/rss/{topic_slug}"

    @classmethod
    def for_topic(cls, topic_slug: str) -> "CIDRAPAdapter":
        return cls(topic_slug)

    async def fetch(self, client: httpx.AsyncClient, days: int) -> list[Alert]:
        try:
            resp = await client.get(self.feed_url, timeout=self.timeout,
                                    headers=self.headers)
            if resp.status_code == 404:
                # Try the alternative pattern
                alt_url = f"https://www.cidrap.umn.edu/{self.topic_slug}/rss.xml"
                logger.info("CIDRAP %s: primary feed URL 404'd, trying %s",
                            self.topic_slug, alt_url)
                resp = await client.get(alt_url, timeout=self.timeout,
                                        headers=self.headers)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("CIDRAP %s fetch failed: %s — check feed URL at "
                           "https://www.cidrap.umn.edu/rss-feeds",
                           self.topic_slug, e)
            return []

        feed = feedparser.parse(resp.text)
        if feed.bozo and not feed.entries:
            logger.warning("CIDRAP %s returned unparseable feed", self.topic_slug)
            return []

        cutoff = date.today() - timedelta(days=days)
        alerts: list[Alert] = []
        for entry in feed.entries:
            published_struct = (getattr(entry, "published_parsed", None)
                                or getattr(entry, "updated_parsed", None))
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

            # CIDRAP summaries are substantive — pass them through to the LLM
            # for accurate clinical summarization and state/county extraction.
            raw_text = " | ".join(filter(None, [
                title,
                entry.get("summary", "")[:1500],
            ]))

            alerts.append(Alert(
                id=self.make_id(self.name, link),
                source=self.name,
                source_type="news",
                title=title,
                url=link,
                published=pub,
                state=None,  # LLM will extract per-article
                category="other",  # LLM will refine
                raw_text=raw_text,
            ))
        logger.info("CIDRAP %s: %d alerts in last %d days",
                    self.topic_slug, len(alerts), days)
        return alerts
