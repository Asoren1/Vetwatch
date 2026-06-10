# VetWatch

**Public health alerts for veterinarians, pulled by location.**

A practicing vet types a state (and optionally a county), picks a lookback
window, and gets a single feed of relevant recalls, outbreaks, advisories,
and regulatory updates from federal, state-ag, and local sources — each
distilled to a 2-sentence clinical summary by an LLM.

Built as an AI summer school exercise. **Demo-quality, not production.** See
[honest limitations](#honest-limitations).

```
┌─ vet types state + county + days back
│
├─ ALL adapters fan out in parallel
│   ├─ openFDA food/drug enforcement (federal recalls)
│   ├─ Texas Animal Health Commission (state-ag)
│   ├─ CIDRAP (4 topic RSS feeds — secondary source for federal data)
│   ├─ Google News RSS, one per state (broad fallback)
│   └─ [stubs] APHIS NLRAD, UC Davis H5 marine, CDFA, NMDA, NVDA,
│              AZDA, LA County DPH, Pima County Health
│
├─ Claude (Haiku by default) enriches each alert:
│   • relevance filter — drop items not vet-actionable
│   • clinical_summary — 2 sentences for a busy practitioner
│   • species tag — affected animals
│   • county extraction from text when not already known
│
└─ frontend renders newest-first, color-coded by source trust level
```

## Setup

Requires Python 3.11+.

```bash
git clone <this-repo>
cd vetwatch
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and paste your ANTHROPIC_API_KEY
# (get one at https://console.anthropic.com/)

uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

Without an Anthropic API key the app still runs — you'll see raw alerts
without clinical summaries or the LLM relevance filter (so you'll see
more noise from Google News).

## Deploying

A `render.yaml` is included for one-click deploy to [Render](https://render.com)'s
free tier:

1. Push this repo to GitHub.
2. In Render, create a new Blueprint and point it at your repo.
3. Render will read `render.yaml`, set up the service, and prompt you for the
   `ANTHROPIC_API_KEY` value (it's marked `sync: false` so you set it in the
   dashboard, never in source control).
4. First deploy takes ~3 minutes. After that, pushes to `main` auto-deploy.

The free tier sleeps after 15 min of inactivity and takes ~30s to wake — fine
for a demo, not for a production tool. For Fly.io, Railway, or a VPS, the same
`uvicorn` start command works; just set `ANTHROPIC_API_KEY` and `PORT` env vars.

## Architecture

```
vetwatch/
├── app/
│   ├── main.py              FastAPI app, /api/alerts endpoint
│   ├── models.py            Alert pydantic model
│   ├── llm/
│   │   └── processor.py     Claude-powered enrichment pipeline
│   └── sources/
│       ├── base.py          BaseAdapter abstract class
│       ├── openfda.py       ✅ FDA food + drug recalls (real API)
│       ├── tahc.py          ✅ Texas Animal Health Commission scraper
│       ├── cidrap.py        ✅ CIDRAP topic RSS feeds
│       ├── google_news.py   ✅ Google News RSS per state
│       └── stubs.py         🚧 Placeholders for sources not yet inspected
├── static/                  Vanilla HTML/CSS/JS frontend
└── tests/
    └── test_smoke.py        No-network smoke tests
```

### Adding a new source

1. Create `app/sources/your_source.py` with a class extending `BaseAdapter`.
2. Implement `async def fetch(self, client, days) -> list[Alert]`.
3. Add an instance to `ALL_ADAPTERS` in `app/sources/__init__.py`.

The TAHC adapter (`app/sources/tahc.py`) is the working reference. It scrapes
HTML, extracts county from titles via regex (no LLM call needed), and
categorizes via keyword heuristics.

### Why some sources are stubs

Writing a scraper without first inspecting the live HTML produces code that
silently returns nothing — that's worse than an honest empty result. Stubs
return `[]` and log their TODO. To unstub:

1. Open the URL in your browser, inspect the press-release section
2. Note the HTML structure (table rows? list items? RSS feed hidden somewhere?)
3. Replace the stub's `fetch()` with a real parser modeled on `tahc.py`

The stubs in `app/sources/stubs.py` each document what's already known about
their source — start there.

## Sources

| Source | Type | Status | Notes |
|---|---|---|---|
| openFDA food enforcement | federal | ✅ implemented | Catches pet food recalls |
| openFDA drug enforcement | federal | ✅ implemented | Catches veterinary drug recalls |
| TAHC | state-ag (TX) | ✅ implemented | Clean structured news page |
| CIDRAP (4 topic feeds) | aggregator | ✅ implemented | High-quality secondary source for federal data |
| Google News (per state) | news | ✅ implemented | Broad fallback for AZ/CA/NM/NV/TX |
| USDA APHIS NLRAD | federal | 🚧 stub | Reportable diseases list; serves as disease taxonomy |
| USDA APHIS HPAI detections | federal | 🚫 robots-blocked | See data routing below |
| USDA APHIS Livestock & Poultry Disease | federal | 🚫 robots-blocked | See data routing below |
| USDA APHIS NWS US confirmed cases | federal | 🚫 robots-blocked | See data routing below |
| screwworm.gov | federal | 🚫 robots-blocked | See data routing below |
| UC Davis H5 Marine Outbreak Tracker | local (CA) | 🚧 stub | Publicly accessible; parseable date-stamped updates |
| CDFA Animal Health | state-ag (CA) | 🚧 stub | Inspect /AHFSS/ for press release feed |
| NM Dept of Ag | state-ag (NM) | 🚧 stub | Hosted at NMSU; locate animal health subpage |
| NV Dept of Ag | state-ag (NV) | 🚧 stub | Initial fetch returned only nav HTML |
| AZ Dept of Ag | state-ag (AZ) | 🚧 stub | Locate Animal Services subpage |
| LA County DPH | local (CA) | 🚧 stub | Both news archive and LAHAN worth pulling |
| Pima County Health | local (AZ) | 🚧 stub | Likely uses CivicAlerts.aspx pattern |

### Data routing for blocked federal sources

USDA publishes a site-wide `robots.txt` that disallows automated agents from
several APHIS pages, including HPAI detections, NWS confirmed cases, the
livestock/poultry disease index, and screwworm.gov. This is a politeness
signal (technically voluntary), but VetWatch respects it. The data itself
is public, and reaches the user through other channels:

**Path 1 — State-ag re-publications.** State animal health agencies typically
re-publish federal HPAI/NWS confirmations within hours, with added local
context. TAHC is the working example; CDFA/AZDA/NMDA/NVDA stubs target the
same pattern. **This is VetWatch's primary path.**

**Path 2 — CIDRAP.** Daily journalism aggregating federal data with citations.
Lag from federal source is typically <72 hours. Four topical feeds wired up:
avian influenza, CWD, AMR, foodborne disease. **Implemented and active.**

**Path 3 — Research data mirrors.** APHIS HPAI flock detection data is
deposited periodically on academic repositories like datalumos.org (UMich).
Snapshot data, not live, but useful for historical context. Not currently
wired up.

**Path 4 — Email subscription ingestion.** TAHC, APHIS, FDA all offer mailing
lists. Subscribing and parsing the mailbox is fully sanctioned. Not currently
wired up.

**Path 5 — Direct link-out.** UI shows "USDA sources for your state" with
deep links the user opens themselves. Zero infrastructure, zero policy risk,
costs the user a click. Not currently wired up.

If you have institutional standing (e.g. AAFSPHV affiliation), it's also
worth asking USDA APHIS directly for API access or an explicit allowance
for an identifiable veterinary tool. They sometimes grant it.

## Honest limitations

- **No production-grade reliability.** Adapters log failures and return empty
  lists rather than crashing, but there's no retry logic, caching, or
  monitoring. A flaky state ag site will silently return nothing.
- **No deduplication across sources.** If TAHC and Google News both report
  the same HPAI detection, you'll see both. (Items from a single source are
  deduped by URL.)
- **Latency.** First scan takes ~5-15 seconds depending on how many adapters
  are wired up. The LLM pass adds ~1-2s per alert at concurrency 5. For a
  real product this needs a background fetcher + cache.
- **No authentication on the API.** Fine for localhost; do not expose to
  the internet without adding auth.
- **No persistence.** Each scan re-fetches everything. Alerts aren't stored.

## Testing

```bash
python -m pytest tests/ -v
```

These tests are deliberately no-network. They verify model shapes, adapter
registration, and the parsing helpers — not live API behavior. Live testing
is manual for now: start the server and try `/api/alerts?state=TX&days=30`.

## License

MIT.
