"""Stub adapters for sources not yet inspected in detail.

Each stub:
- Documents the source URL and what's known about it
- Returns [] from fetch() until implemented
- Logs at INFO level so it's obvious in the server log that the stub is in use

To implement a stub, replace the body of fetch() with a real parser. The TAHC
adapter (app/sources/tahc.py) is a working reference.

Why stubs instead of best-guess scrapers:
  Writing a scraper without first inspecting the live HTML structure produces
  code that silently returns nothing — worse than an honest empty result,
  because it looks like the source has nothing to say. Stubs are honest.
"""
from __future__ import annotations

import logging

import httpx

from app.models import Alert
from app.sources.base import BaseAdapter

logger = logging.getLogger(__name__)


class _StubAdapter(BaseAdapter):
    """Shared base for unimplemented adapters. Logs once per fetch."""

    endpoint = ""
    notes = ""

    async def fetch(self, client: httpx.AsyncClient, days: int) -> list[Alert]:
        logger.info(
            "[stub] %s adapter not yet implemented. Source: %s. Notes: %s",
            self.name, self.endpoint, self.notes or "(none)",
        )
        return []


class APHISReportableDiseasesAdapter(_StubAdapter):
    name = "USDA APHIS NLRAD"
    source_type = "federal"
    state = None
    endpoint = "https://www.aphis.usda.gov/livestock-poultry-disease/surveillance/reportable-diseases"
    notes = (
        "Provides the National List of Reportable Animal Diseases. The page is "
        "paginated (?page=1, ?page=2). When implemented, this serves dual purpose: "
        "(a) a data source for new APHIS notifications, and (b) a controlled "
        "vocabulary for tagging entries from other adapters."
    )


class ScrewwormGovAdapter(_StubAdapter):
    name = "screwworm.gov"
    source_type = "federal"
    state = None
    endpoint = "https://screwworm.gov/"
    notes = (
        "Robots.txt disallows automated fetching. Three honest options: (1) ask "
        "USDA for an API or an explicit allowance, (2) link out to the site in the "
        "UI without scraping, (3) ingest the daily PDF reports if/when they're "
        "available on an allowed domain. Current implementation does nothing."
    )


class LACountyDPHAdapter(_StubAdapter):
    name = "LA County DPH"
    source_type = "local"
    state = "CA"
    endpoint = "http://publichealth.lacounty.gov/phcommon/public/media/mediapubdisplay.cfm?unit=media&ou=ph&prog=media"
    notes = (
        "News release archive. Also worth pulling http://publichealth.lacounty.gov/lahan/ "
        "for clinical alerts directed at health professionals (closer match to vet workflow). "
        "Inspect the archive HTML to find date+title+link rows."
    )


class PimaCountyHealthAdapter(_StubAdapter):
    name = "Pima County Health"
    source_type = "local"
    state = "AZ"
    endpoint = "https://www.pima.gov/2031/Health"
    notes = (
        "County health department landing page. Press releases live under a different "
        "URL — typically /CivicAlerts.aspx?CID=... — inspect the landing page for the "
        "actual feed location. Pima County is the reference county per project scope."
    )


class CDFAAnimalHealthAdapter(_StubAdapter):
    name = "CDFA Animal Health"
    source_type = "state-ag"
    state = "CA"
    endpoint = "https://www.cdfa.ca.gov/AHFSS/"
    notes = (
        "California Animal Health and Food Safety Services. Forms & Publications page "
        "(provided URL) is largely forms, not news. The main /AHFSS/ landing page "
        "carries disease updates — inspect for press release feed."
    )


class NMDAAdapter(_StubAdapter):
    name = "NM Dept of Ag"
    source_type = "state-ag"
    state = "NM"
    endpoint = "https://nmdeptag.nmsu.edu/"
    notes = (
        "New Mexico Department of Agriculture (hosted at NMSU). Animal health updates "
        "section needs to be located — likely under /animal-and-plant-protection/ or "
        "similar. Inspect the live site."
    )


class NVDAAdapter(_StubAdapter):
    name = "NV Dept of Ag"
    source_type = "state-ag"
    state = "NV"
    endpoint = "https://agri.nv.gov/Animals/Animal_Disease/Animal_Disease_Updates/"
    notes = (
        "Animal Disease Updates page. NOTE: an initial fetch returned only navigation "
        "HTML, suggesting the actual content sits in a dynamically-loaded panel or is "
        "minimal. Inspect with browser devtools before writing a parser. "
        "May also be worth pulling /Outreach/News/ for general news releases."
    )


class AZDAAdapter(_StubAdapter):
    name = "AZ Dept of Ag"
    source_type = "state-ag"
    state = "AZ"
    endpoint = "https://agriculture.az.gov/"
    notes = (
        "Arizona Department of Agriculture. Animal Services Division publishes disease "
        "alerts but the specific URL needs to be located. Try /animal-services/ or "
        "/divisions/animal-services-division/."
    )


class APHISHPAIDetectionsAdapter(_StubAdapter):
    name = "APHIS HPAI Detections (Commercial/Backyard)"
    source_type = "federal"
    state = None
    endpoint = "https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza/hpai-detections/commercial-backyard-flocks"
    notes = (
        "BLOCKED BY ROBOTS.TXT — same restriction as screwworm.gov and the APHIS "
        "general livestock disease page. USDA enforces this site-wide. Alternatives "
        "to investigate: (a) USDA APHIS RSS feeds if any exist for HPAI specifically, "
        "(b) the USDA Animal Disease Notification System email list, (c) state-level "
        "HPAI reporting (CDFA, TAHC already capture state-confirmed cases). Until then "
        "the Google News fallback will catch most major HPAI announcements."
    )


class APHISLivestockPoultryAdapter(_StubAdapter):
    name = "APHIS Livestock & Poultry Disease"
    source_type = "federal"
    state = None
    endpoint = "https://www.aphis.usda.gov/animals/animal-health/livestock-and-poultry-disease"
    notes = (
        "BLOCKED BY ROBOTS.TXT (same as above). This is the general APHIS animal "
        "health page covering all livestock/poultry diseases beyond HPAI. Needs the "
        "same alternative-ingestion solution as the HPAI page."
    )


class APHISNWSConfirmedCasesAdapter(_StubAdapter):
    name = "APHIS NWS US Confirmed Cases"
    source_type = "federal"
    state = None
    endpoint = "https://www.aphis.usda.gov/animals/animal-health/livestock-and-poultry-disease/current-status/us-confirmed-cases-new-world"
    notes = (
        "BLOCKED BY ROBOTS.TXT — same APHIS-wide restriction. Federal counterpart to "
        "the state-by-state TAHC NWS reports — likely contains confirmed cases across "
        "all US states with location detail. High value if we can find an ingestion "
        "path. Until then, TAHC + Google News covers Texas (where the active outbreak "
        "is); add similar state-ag scrapers for affected states as NWS spreads."
    )


class UCDavisH5MarineAdapter(_StubAdapter):
    name = "UC Davis H5 Marine Outbreak Tracker"
    source_type = "local"  # CA-specific surveillance
    state = "CA"
    endpoint = "https://pandemicinsights.ucdavis.edu/h5-marine-outbreak"
    notes = (
        "UC Davis Institute for Pandemic Insights live tracker for H5N1 in California "
        "marine mammals. Publicly accessible (unlike APHIS). Format is one long page "
        "with chronological update paragraphs prefixed by date (e.g. '03/26/2026: "
        "Scientists have confirmed a case of HPAI H5N1 in a California sea lion in "
        "San Luis Obispo County...'). Implementation plan: fetch page, regex on "
        "r'^(\\d{2}/\\d{2}/\\d{4}):\\s+(.+?)(?=^\\d{2}/\\d{2}/\\d{4}:|\\Z)' across the "
        "main content div, treat each match as one Alert. Counties (San Mateo, San "
        "Luis Obispo) are typically explicit in the text — let the LLM extract."
    )
