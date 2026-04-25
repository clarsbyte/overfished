# Vessel-incursion IUU pipeline

Multi-agent backend that takes a coordinate (and optionally a known MMSI / port country) and produces a citation-backed **evidence document** describing whether the vessels at that location are likely engaged in illegal, unreported, or unregulated (IUU) fishing — what laws may have been broken, what penalties apply, and what enforcement options the receiving port authority has.

The trigger is "a supposed vessel is entering region X." The pipeline runs three live data layers in parallel (AIS, SAR, regional law) plus a per-vessel IUU history layer, then a supervisor LLM synthesizes the result.

---

## Architecture

```
                       ┌──────────────────────────────────────┐
                       │           pipeline_agent.py          │
                       │  Supervisor (Claude Sonnet 4.6)      │
                       └───────────┬───────────┬───────────┬──┘
                                   │           │           │
              ┌────────────────────┘           │           └─────────────────┐
              │  (turn 1, parallel tool_use)   │                             │
              ▼                                ▼                             ▼
   ┌─────────────────────┐      ┌─────────────────────┐      ┌──────────────────────┐
   │ check_ais_at_       │      │ find_dark_targets_  │      │ lookup_regional_     │
   │ location(coords)    │      │ in_region(coords)   │      │ laws(coords)         │
   │                     │      │                     │      │                      │
   │  vessel_lookup →    │      │  gfw_lookup →       │      │  regional_agent →    │
   │  AISStream WS       │      │  4Wings SAR API     │      │  ProtectedSeas live  │
   │  (live AIS bbox)    │      │  (Sentinel-1 radar) │      │  + cached FAOLEX/    │
   │                     │      │                     │      │    FISHLEX/PORTLEX   │
   │  → MMSI list        │      │  → SAR count        │      │  → legal dossier     │
   └────────┬────────────┘      └─────────────────────┘      └──────────────────────┘
            │
            │  (turn 2, branch)
            │
       ┌────┴────────────────────────────────────────┐
       │                                              │
       │  CASE A: AIS returned MMSIs                  │  CASE B: AIS silent
       │   → classify_vessel_iuu(mmsi)                │   → find_historical_vessels_in_region
       │     ×6 in parallel                           │     → classify_vessel_iuu(mmsi) ×6
       │                                              │
       └─────────────────────┬────────────────────────┘
                             │
                             ▼  (turn 3, synthesis)
              ┌─────────────────────────────────────┐
              │   EVIDENCE OF POTENTIAL IUU         │
              │   FISHING ACTIVITY                  │
              │   (the deliverable — text doc       │
              │    formatted for forwarding to a    │
              │    port authority)                  │
              └─────────────────────────────────────┘
```

**Inter-agent identity contract: MMSI only.** Vessel names cause fuzzy-match failures in GFW search (we observed "STS-50" matching "SAVE THE SOUND" during development). Both vessel_agent and the historical-events fallback emit lines that begin with `MMSI=<9-digit>`, and the `classify_vessel_iuu` tool is typed `mmsi: str` with a hard rule in its docstring.

---

## Data sources & provenance

Every claim in the evidence document carries `source_url` + `last_checked` + `confidence` so the output can be defended in audit. Three confidence levels are used:

| Confidence | Meaning |
|---|---|
| `live` | Queried from a public API at request time (ProtectedSeas, AISStream, GFW). |
| `extracted` | Pulled from a structured data dump (e.g., FAOLEX CSV). Not yet wired — see Limitations. |
| `curated` | Hand-curated from public sources (FAO databases) but not directly cross-referenced to a database record. |

| Source | Layer | API | Confidence | Used for |
|---|---|---|---|---|
| **AISStream.io** | Live AIS broadcasts | WebSocket bbox subscription | `live` | "Who is broadcasting AIS at this location right now?" |
| **Global Fishing Watch — Vessels** | Per-vessel identity | REST `/v3/vessels/search` | `live` | Identity, ownership, RFMO authorizations |
| **Global Fishing Watch — Insights** | Per-vessel IUU risk | REST `/v3/insights/vessels` | `live` | RFMO IUU list match, AIS gaps, fishing in MPAs, fishing without authorization, AIS coverage % |
| **Global Fishing Watch — Events** | Per-vessel events | REST `/v3/events` | `live` | FISHING / GAP / ENCOUNTER / LOITERING / PORT_VISIT events with regions intersected |
| **Global Fishing Watch — Events (region)** | Region-bbox events | POST `/v3/events` with GeoJSON | `live` | Dark-vessel fallback: vessels GFW saw active in this region (incl. recent AIS-off) |
| **Global Fishing Watch — 4Wings SAR** | Satellite radar | POST `/v3/4wings/report` | `live` | Vessel detections via Sentinel-1 SAR — sees vessels regardless of AIS broadcast |
| **ProtectedSeas Navigator** | MPA / fishing-protection | ArcGIS FeatureServer | `live` | Maximum Level of Fishing Protection (1–5) at any coordinate |
| **FAOLEX** | Source legislation | curated cache (`data/regional_rules.json`) | `curated` | Per-region key law titles, citations, search URLs |
| **FISHLEX** | Foreign-vessel rules | curated cache | `curated` | License/gear/area/reporting/observer/transshipment/penalties/access-agreement fields per coastal state |
| **PORTLEX** | Port state measures | curated cache | `curated` | PSMA party status, designated ports, advance notice, inspection powers, denial grounds, required documents |

The curated cache currently covers three demo regions: Galápagos Marine Reserve (Ecuador), Philippines EEZ (with Tubbataha and closed seasons), and EU Western Mediterranean (with the GFCM management area). Coordinate → coastal-state resolution today is a coarse bbox lookup against the cache; production should swap that for a Marine Regions World EEZ polygon query.

---

## Modules

| File | Role |
|---|---|
| `pipeline_agent.py` | Supervisor agent — multi-agent orchestration + evidence-document synthesis. |
| `vessel_agent.py` | Subagent — wraps the AISStream live lookup. |
| `gfw_agent.py` | Subagent — IUU risk classifier per vessel using GFW Insights/Events/Vessels. |
| `regional_agent.py` | Subagent — citation-backed legal dossier (ProtectedSeas + FAOLEX/FISHLEX/PORTLEX). |
| `vessel_lookup.py` | Pure Python — AISStream WebSocket client, haversine, bbox helpers. |
| `gfw_lookup.py` | Pure Python — GFW v3 REST client (Vessels/Insights/Events) + region-events + 4Wings SAR. |
| `regional_lookup.py` | Pure Python — composes ProtectedSeas live overlay with cached coastal-state rules. |
| `protectedseas_arcgis.py` | Pure Python — ProtectedSeas Global Max LFP ArcGIS FeatureServer client. |
| `data/regional_rules.json` | Curated FAOLEX/FISHLEX/PORTLEX cache for the three demo regions. |

### Supervisor tools

| Tool | Wraps | Purpose |
|---|---|---|
| `check_ais_at_location` | `vessel_lookup.vessels_within_radius` | Live AIS bbox query; returns `MMSI=…`-prefixed vessel lines |
| `find_dark_targets_in_region` | `gfw_lookup.get_sar_detections_in_region` | SAR detection count for the bbox; no MMSI |
| `lookup_regional_laws` | `regional_agent.evaluate_point` | Full legal dossier with citations |
| `classify_vessel_iuu` | `gfw_agent.classify_vessel` | Per-vessel IUU verdict; **MMSI-only contract** |
| `find_historical_vessels_in_region` | `gfw_lookup.get_events_in_region` | AIS-silent fallback: returns top-6 unique MMSIs from GFW events |

---

## Setup

### Environment

Copy `.env.example` to `.env` and fill in:

```
ANTHROPIC_API_KEY=...      # Claude API key (api.anthropic.com)
AISSTREAM_API_KEY=...      # https://aisstream.io  (free)
GFW_API_TOKEN=...          # https://globalfishingwatch.org/our-apis/  (free, manual approval)
```

### Install

```bash
cd backend
pip install -r requirements.txt
```

LangChain is pinned `>=0.3,<1.0` because the v1 release moved `AgentExecutor` and `create_tool_calling_agent` out of `langchain.agents` into `langchain-classic`. Migrating to LangGraph is a clean follow-up.

---

## Running

### End-to-end pipeline

```bash
# Tubbataha Reefs (no-take MPA, Philippines)
python pipeline_agent.py 8.85 119.917 --port-country PHL

# Galápagos Marine Reserve
python pipeline_agent.py -1.385 -91.821 --port-country ECU

# Port of LA — busy AIS, regions uncached (will return INSUFFICIENT_DATA on legal context)
python pipeline_agent.py 33.74 -118.26

# With a known MMSI from the trigger event
python pipeline_agent.py 8.85 119.917 --port-country PHL --mmsi 412440493
```

CLI flags:

| Flag | Default | Purpose |
|---|---|---|
| `<lat> <lon>` | required | sighting coordinate |
| `--radius` | `50` mi | search radius for AIS / SAR / dark-vessel events |
| `--port-country` | none | ISO3 port code (PHL, ECU, EU, …) — populates PORTLEX |
| `--mmsi` | none | known MMSI from the trigger; classified directly in addition to AIS-discovered set |

### Smoke tests (no LLM)

| Script | Tests |
|---|---|
| `python test.py` | AISStream live bbox query (Port of LA default) |
| `python test_gfw.py "<query>"` | GFW search → insights → events for a vessel name/MMSI |
| `python test_gfw_region.py` | GFW Events region-bbox query (the AIS-silent fallback) |
| `python test_gfw_sar.py` | GFW 4Wings SAR detection query (the dark-target tool) |
| `python test_regional.py` | ProtectedSeas LFP + cached FISHLEX/PORTLEX/FAOLEX dossier |

### End-to-end with LLM

```bash
python test_pipeline.py             # Port of LA + Tubbataha
python test_pipeline.py tubbataha   # one scenario only
```

---

## Output: the evidence document

The supervisor returns a fixed-format text block:

```
EVIDENCE OF POTENTIAL IUU FISHING ACTIVITY
==========================================
INCIDENT LOCATION: ...
ASSEMBLED AT: ...

AIS STATUS AT LOCATION:
- Vessels broadcasting AIS:           N
- SAR-detected vessels:               M
- DARK TARGET GAP:                    max(0, M - N)   ← red flag if > 0

VESSELS INVESTIGATED:
1. <name> (MMSI ..., flag ...)
   IUU VERDICT: <HIGH|MEDIUM|LOW|INSUFFICIENT_DATA>
   Evidence:
   - ...
2. ...

LEGAL CONTEXT:
- Coastal state, ProtectedSeas LFP, key applicable rules with citations

LAWS POTENTIALLY BREACHED (per vessel):
- ...

PENALTIES (FISHLEX):
- ...

RECOMMENDED ACTIONS:
- Notify competent authority
- Port denial grounds
- Required documents to demand on inspection

SOURCES:
- AIS, GFW, ProtectedSeas, FAOLEX/FISHLEX/PORTLEX URLs with last_checked

CAVEATS:
- GFW indicators reflect "apparent" activity, not adjudicated illegal fishing
- Regional rules are curated, pending FAOLEX CSV ingestion
- AIS absence is suggestive but not conclusive
```

The "next-action" piece — actually contacting the port authority — is intentionally out of scope. The document is the deliverable.

---

## Latency

A single end-to-end run is ~60–180 s depending on AIS density and how many vessels need IUU classification. Breakdown:

| Stage | Time | Why |
|---|---|---|
| AISStream listen | 30 s | Stream subscription window — controlled by `listen_seconds` |
| Regional dossier | 5–10 s | One LLM hop in `regional_agent` |
| 4Wings SAR | 1–3 s | Single REST call |
| Per-vessel IUU classify (×6) | 30–60 s each | Each call fans out to GFW Vessels / Insights / Events plus an LLM hop |
| Supervisor synthesis | 5–10 s | Final LLM hop on Sonnet 4.6, 8192 max tokens |

Switching the supervisor to Haiku 4.5 for the synthesis step is a one-line change that cuts ~30 s off latency without affecting decision quality (synthesis is mechanical formatting).

---

## Known limitations

1. **FAOLEX CSV ingestion not wired.** Currently every `record_id` is `null` and `confidence` is `curated`. Downloading the FAOLEX Open Data CSV, filtering to fisheries/marine/IUU subjects, and replacing each cached `key_records` entry with the actual `LEX-FAOC...` permalink would flip those entries to `confidence: extracted`.
2. **Coastal-state resolution is a bbox lookup, not an EEZ polygon.** Coordinates near contested boundaries can mis-classify. Production swap: Marine Regions World EEZ WFS.
3. **FISHLEX/PORTLEX live extraction not wired.** The structured field schema in `regional_rules.json` is designed so a per-country scrape of FAO's HTML tables can drop into the same fields without restructuring.
4. **SAR returns a count, not per-detection positions.** The 4Wings `/report` endpoint aggregates. If you need lat/lon per detection (to correlate spatially with each AIS broadcast), use the underlying SAR bin/raster data — bigger refactor.
5. **GFW "apparent" caveat.** Every IUU signal from GFW is inferred from AIS patterns; none is adjudicated. The supervisor states this explicitly in CAVEATS but downstream callers should not treat the verdict as legal proof.
6. **LangChain 0.3.x pinned.** v1 migration (LangGraph + langchain-classic) is a clean follow-up.

---

## File layout

```
backend/
├── README.md                      # this file
├── requirements.txt
├── .env.example
│
├── pipeline_agent.py              # ← multi-agent supervisor (entry point)
├── vessel_agent.py                # AISStream subagent
├── gfw_agent.py                   # GFW IUU subagent
├── regional_agent.py              # FAO/ProtectedSeas subagent
│
├── vessel_lookup.py               # AISStream client
├── gfw_lookup.py                  # GFW REST client (vessels/insights/events/sar)
├── regional_lookup.py             # composer: ProtectedSeas + cached rules
├── protectedseas_arcgis.py        # ProtectedSeas FeatureServer client
│
├── data/
│   └── regional_rules.json        # curated FAOLEX/FISHLEX/PORTLEX cache
│
├── test.py                        # AISStream smoke
├── test_gfw.py                    # GFW per-vessel smoke
├── test_gfw_region.py             # GFW Events region-bbox smoke
├── test_gfw_sar.py                # GFW 4Wings SAR smoke
├── test_regional.py               # regional dossier smoke
└── test_pipeline.py               # full end-to-end pipeline smoke
```
