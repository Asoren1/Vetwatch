"""LLM enrichment pipeline.

What we ask Claude to do, per alert:
  1. relevance: is this actually useful for a practicing veterinarian? (yes/no)
  2. clinical_summary: 2 sentences a vet can read in 5 seconds — what it is,
     what to watch for, what to do clinically.
  3. species: which animal species/groups are affected
  4. county: if mentioned in the text but not extracted by the adapter

We batch these into a single API call per alert to keep latency reasonable.
Alerts already filtered out by the adapter (e.g. TAHC's existing county
extraction) skip the geo step automatically.

Failure mode: if the LLM call fails, the alert is returned UNMODIFIED. It still
appears in the UI, just without a clinical summary. The UI should show the raw
title and link out — never block on LLM failures.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from anthropic import AsyncAnthropic, APIError

from app.models import Alert

logger = logging.getLogger(__name__)

# Default to Haiku for cost/latency; override with CLAUDE_MODEL env var.
DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# How many alerts to enrich concurrently. Tune up if rate limits allow.
CONCURRENCY = 5


SYSTEM_PROMPT = """You are an assistant helping practicing veterinarians scan public health alerts.

For each alert you receive, you must respond with a single JSON object and nothing else (no prose, no code fences). Schema:

{
  "relevant": boolean,           // true if a typical veterinarian in clinical practice would find this useful or actionable
  "clinical_summary": string,    // 2 sentences max. Plain English. What is it, and what should the vet watch for or do.
  "species": [string],           // affected species/groups, lowercase, e.g. ["cattle", "dairy"]. Empty array if none specified.
  "county": string or null,      // county name (no "County" suffix) if explicitly mentioned in the text, else null
  "category": string             // one of: "recall", "outbreak", "advisory", "regulatory", "other"
}

Rules:
- Be conservative on relevance. A general news item that does not affect clinical practice is relevant=false.
- Do not invent facts. If species or county aren't in the text, return empty/null.
- Clinical summary should never be longer than 2 sentences."""


class LLMProcessor:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.client: Optional[AsyncAnthropic] = None
        if self.api_key:
            self.client = AsyncAnthropic(api_key=self.api_key)
        else:
            logger.warning(
                "ANTHROPIC_API_KEY not set — LLM enrichment disabled, "
                "alerts will be returned without summaries."
            )

    async def enrich(self, alerts: list[Alert]) -> list[Alert]:
        """Returns the same alerts, enriched in place. Drops irrelevant ones."""
        if not self.client:
            return alerts

        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def _process(alert: Alert) -> Optional[Alert]:
            async with semaphore:
                return await self._enrich_one(alert)

        results = await asyncio.gather(*[_process(a) for a in alerts])
        return [r for r in results if r is not None]

    async def _enrich_one(self, alert: Alert) -> Optional[Alert]:
        """Returns the enriched alert, or None if the LLM marked it irrelevant."""
        text_for_llm = "\n".join(filter(None, [
            f"Title: {alert.title}",
            f"Source: {alert.source} ({alert.source_type})",
            f"Source state: {alert.state or 'national'}",
            f"Source county: {alert.county or 'unspecified'}",
            f"Content: {alert.raw_text or alert.title}",
        ]))

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=400,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text_for_llm}],
            )
            raw = response.content[0].text.strip()
            # Strip code fences if Claude added them despite instructions
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw
                raw = raw.rsplit("```", 1)[0]
            parsed = json.loads(raw)
        except (APIError, json.JSONDecodeError, IndexError, AttributeError) as e:
            logger.warning("LLM enrichment failed for alert %s: %s", alert.id, e)
            return alert  # return UNENRICHED — don't drop on failure

        if not parsed.get("relevant", True):
            return None

        alert.clinical_summary = parsed.get("clinical_summary") or alert.clinical_summary
        alert.species = parsed.get("species") or alert.species
        if not alert.county and parsed.get("county"):
            alert.county = parsed["county"]
        if alert.category == "other" and parsed.get("category"):
            alert.category = parsed["category"]
        return alert
