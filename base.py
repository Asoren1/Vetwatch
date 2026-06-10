"""Adapter base class.

Every data source (FDA, TAHC, APHIS, etc.) subclasses BaseAdapter and
implements `fetch()`. The pipeline collects results from all enabled
adapters, then enriches them via the LLM, then serves them through the API.

Design notes
------------
- Adapters MUST be resilient to network errors and structural changes.
  Return an empty list and log the failure rather than raising.
- Adapters MUST NOT call the LLM. Enrichment happens in app.llm.processor.
- Adapters MUST set Alert.id to something stable so duplicate fetches
  don't create duplicate entries (a hash of source+url is usually right).
"""
from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from app.models import Alert

logger = logging.getLogger(__name__)


class AdapterError(Exception):
    """Raised when an adapter cannot fetch — caller should treat as 'no results' not 'crash'."""


class BaseAdapter(ABC):
    """Subclass this for each new data source."""

    # Subclasses override these
    name: str = "Unnamed"                # e.g. "TAHC"
    source_type: str = "federal"         # one of: federal, state-ag, state-health, local, news
    state: Optional[str] = None          # two-letter code if source is state-scoped, else None
    enabled: bool = True

    # Shared HTTP client config — adapters can override
    timeout = httpx.Timeout(15.0, connect=5.0)
    headers = {
        "User-Agent": "VetWatch/0.1 (public health surveillance aggregator; "
                      "https://github.com/example/vetwatch)"
    }

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient, days: int) -> list[Alert]:
        """Return alerts published in the last `days` days.

        Adapters should:
        - Catch their own exceptions and return [] on failure (with logger.warning)
        - Not return alerts older than `days` (but the API will re-filter anyway)
        - Set Alert.county when extractable from source data (avoids LLM cost)
        """
        ...

    @staticmethod
    def make_id(source: str, url: str) -> str:
        """Stable ID for deduplication."""
        return hashlib.sha1(f"{source}|{url}".encode()).hexdigest()[:16]
