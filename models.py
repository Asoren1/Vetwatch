"""Core data model for a public health alert relevant to veterinarians."""
from __future__ import annotations

from datetime import date, datetime, UTC
from typing import Literal, Optional
from pydantic import BaseModel, Field


AlertCategory = Literal[
    "recall",          # FDA / USDA recall
    "outbreak",        # confirmed disease detection
    "advisory",        # advisory or guidance (e.g. enhanced biosecurity)
    "regulatory",      # rule changes, movement restrictions, EDOs
    "other",
]


class Alert(BaseModel):
    """A single public health alert.

    Adapters produce these; the LLM pipeline enriches them; the API serves them.
    All fields except those marked Optional must be set by the adapter — the LLM
    pipeline only fills clinical_summary, species, category (if missing), and
    county (if extractable from text).
    """

    # --- Required: set by adapter ---
    id: str = Field(description="Stable unique ID — typically source + URL hash")
    source: str = Field(description="Human-readable source name, e.g. 'TAHC'")
    source_type: Literal["federal", "state-ag", "state-health", "local", "news"] = Field(
        description="Used for UI grouping and trust indicators"
    )
    title: str
    url: str = Field(description="Canonical link to the original announcement")
    published: date = Field(description="Publication date as reported by the source")

    # --- Geographic scope ---
    state: Optional[str] = Field(
        default=None,
        description="Two-letter state code (e.g. 'TX'). None means federal/national scope.",
    )
    county: Optional[str] = Field(
        default=None,
        description="County name without 'County' suffix, e.g. 'Pima'. May be LLM-extracted.",
    )
    latitude: Optional[float] = Field(
        default=None,
        description="Resolved lat for map display. Set by the API layer after LLM enrichment.",
    )
    longitude: Optional[float] = Field(
        default=None,
        description="Resolved lng for map display. Set by the API layer after LLM enrichment.",
    )
    geo_resolution: Optional[str] = Field(
        default=None,
        description="How precise the geo is: 'county', 'state', or None for unmapped.",
    )

    # --- Classification ---
    category: AlertCategory = "other"
    species: list[str] = Field(
        default_factory=list,
        description="Affected species/groups (e.g. ['cattle', 'dairy']) — may be LLM-tagged",
    )

    # --- Clinical content ---
    raw_text: Optional[str] = Field(
        default=None,
        description="Original text snippet from the source (used as LLM input, not displayed)",
    )
    clinical_summary: Optional[str] = Field(
        default=None,
        description="2-sentence LLM-generated summary aimed at a practicing vet. "
                    "Populated by the LLM pipeline, not the adapter.",
    )

    # --- Metadata ---
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def matches_filter(
        self,
        state: Optional[str] = None,
        county: Optional[str] = None,
        days: Optional[int] = None,
    ) -> bool:
        """Used by the API to filter results before returning to the client."""
        if state and self.state and self.state != state:
            # Federal alerts (state is None) always pass the state filter
            return False
        if county and self.county and self.county.lower() != county.lower():
            return False
        if days is not None:
            age = (date.today() - self.published).days
            if age > days:
                return False
        return True
