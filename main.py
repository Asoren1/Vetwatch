"""FastAPI app.

Endpoints:
  GET /api/alerts?state=TX&county=Zavala&days=30  — JSON list of enriched alerts
  GET /api/sources                                — list of configured sources + status
  GET /                                          — serves the frontend

The /api/alerts endpoint fans out to every adapter in parallel, then runs the
LLM enrichment pass on the combined results, then filters by the query params
and returns sorted by date (newest first).
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.llm.processor import LLMProcessor
from app.models import Alert
from app.sources import ALL_ADAPTERS, SUPPORTED_STATES

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="VetWatch",
    description="Public health alerts for veterinarians, by location.",
    version="0.1.0",
)


STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Shared LLM processor (single instance, reused across requests)
llm = LLMProcessor()


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/sources")
async def list_sources():
    """Used by the UI to show what's wired up vs what's stubbed."""
    return {
        "supported_states": SUPPORTED_STATES,
        "sources": [
            {
                "name": a.name,
                "type": a.source_type,
                "state": a.state,
                "implemented": not a.__class__.__name__.startswith("_")
                               and "Stub" not in a.__class__.__name__
                               and not a.__class__.__module__.endswith(".stubs"),
            }
            for a in ALL_ADAPTERS
        ],
    }


@app.get("/api/alerts")
async def get_alerts(
    state: Optional[str] = Query(None, description="Two-letter state code, e.g. 'TX'"),
    county: Optional[str] = Query(None, description="County name without 'County' suffix"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
) -> dict:
    """Aggregate from all sources, enrich, filter, return."""

    # Only call adapters that might return results for this state filter.
    # Federal adapters (state=None) are always called.
    # State-specific adapters are called only if their state matches.
    relevant_adapters = [
        a for a in ALL_ADAPTERS
        if a.enabled and (a.state is None or state is None or a.state == state)
    ]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        adapter_results = await asyncio.gather(
            *[a.fetch(client, days) for a in relevant_adapters],
            return_exceptions=True,
        )

    raw_alerts: list[Alert] = []
    adapter_status = []
    for adapter, result in zip(relevant_adapters, adapter_results):
        if isinstance(result, Exception):
            logger.warning("Adapter %s raised: %s", adapter.name, result)
            adapter_status.append({"name": adapter.name, "status": "error",
                                    "error": str(result)})
            continue
        adapter_status.append({"name": adapter.name, "status": "ok",
                                "count": len(result)})
        raw_alerts.extend(result)

    # Deduplicate by id (in case multiple adapters return the same item)
    seen: set[str] = set()
    deduped: list[Alert] = []
    for a in raw_alerts:
        if a.id in seen:
            continue
        seen.add(a.id)
        deduped.append(a)

    # LLM enrichment (drops irrelevant items)
    enriched = await llm.enrich(deduped)

    # Geo-resolution: now that LLM has populated county where extractable,
    # look up lat/lng from our centroid table.
    from app.data.centroids import resolve_coordinates, COUNTY_CENTROIDS
    for a in enriched:
        coords = resolve_coordinates(a.state, a.county)
        if coords:
            a.latitude, a.longitude = coords
            key = (a.state, (a.county or "").lower().strip())
            a.geo_resolution = "county" if key in COUNTY_CENTROIDS else "state"

    # Final filter (LLM may have set county; re-apply user filter)
    filtered = [a for a in enriched if a.matches_filter(state=state, county=county, days=days)]

    # Sort newest first
    filtered.sort(key=lambda a: a.published, reverse=True)

    return {
        "count": len(filtered),
        "filters": {"state": state, "county": county, "days": days},
        "adapter_status": adapter_status,
        "alerts": [a.model_dump(mode="json") for a in filtered],
    }
