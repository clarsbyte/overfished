"""Playwright-rendered FAOLEX scraper + gemma3 law summarizer.

Pipeline per country (one Playwright session shared across all renders):
  1. Render the search SPA at:
       https://www.fao.org/faolex/results/en/?country=<ISO3>&subject=Fisheries
       #querystring=<base64(search=<country> fisheries&yearFrom=&yearTo=&endstring=1)>
     The fragment-search keyword is mandatory — the URL `country=` filter
     alone returns 0 records when the SPA's keyword is empty.
  2. Parse the rendered search text into N (id, title, year, type, abstract,
     detail_url) records.
  3. For each record, render its detail_url and extract <main> text — that
     is the actual statute body the LLM needs to reason about.
  4. Run gemma3:4b over each statute body to extract structured rules
     (prohibitions / gear / area / penalties / IUU relevance / citation
     quote) so the regional_agent can cite specific clauses instead of
     just naming the law.
  5. Cache the entire enriched record list to data/faolex_cache/<iso3>.json
     keyed by (iso3, subject, search). Cached calls are <50 ms; first crawl
     is ~30-60 s for 10 records.

Designed to fail soft: if Playwright is missing, chromium isn't installed,
or the LLM ping fails, the function returns whatever layers it could fill
(at minimum the search URL and any partial records) so the regional dossier
still has a citation.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

CACHE_DIR = Path(__file__).parent / "data" / "faolex_cache"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # 7 days
RECORDS_CAP = 10  # one search-result page
DETAIL_TEXT_TRIM_CHARS = 14000  # cap per-statute text before LLM summarization
DETAIL_TEXT_CACHE_CHARS = 20000  # what we keep on disk per record

_LEX_RE = re.compile(r"LEX-FAO[CS]\d{5,8}")
_LEX_ID_RE = re.compile(r"^(LEX-FAO[CS]\d{5,8})$")
_NO_HEADER = "FAOLEX No:"
_YEAR_HEADER = "By Year:"
_TYPE_HEADER = "By Type Of Text:"
_FAO_CHROME_IDS = {"LEX-FAOC130388"}
_DETAIL_URL = "https://www.fao.org/faolex/results/details/en/c/{id}/"

_FAO_CHROME_LINES = {
    "FAO.org", "العربية", "中文", "﻿中文", "English", "Français",
    "Русский", "Español", "FAOLEX Database", "Background", "Country Profiles",
    "Thematic Databases", "Associated Databases", "Highlights", "Glossary",
    "COVID-19", "Open Data", "ADVANCED SEARCH", "Sort by relevance",
    "Sort by date",
}
_FAO_CHROME_PREFIXES = ("Showing ",)

_ISO3_TO_NAME = {
    "ARG": "Argentina", "AUS": "Australia", "BEL": "Belgium",
    "BRA": "Brazil",    "CAN": "Canada",    "CHL": "Chile",
    "CHN": "China",     "COL": "Colombia",  "CUB": "Cuba",
    "DEU": "Germany",   "DNK": "Denmark",   "ECU": "Ecuador",
    "ESP": "Spain",     "FJI": "Fiji",      "FRA": "France",
    "GBR": "United Kingdom", "GHA": "Ghana", "GRC": "Greece",
    "HRV": "Croatia",   "IDN": "Indonesia", "IND": "India",
    "IRL": "Ireland",   "ISL": "Iceland",   "ITA": "Italy",
    "JPN": "Japan",     "KEN": "Kenya",     "KOR": "Korea",
    "LKA": "Sri Lanka", "MAR": "Morocco",   "MDG": "Madagascar",
    "MEX": "Mexico",    "MYS": "Malaysia",  "MOZ": "Mozambique",
    "NAM": "Namibia",   "NGA": "Nigeria",   "NLD": "Netherlands",
    "NOR": "Norway",    "NZL": "New Zealand", "OMN": "Oman",
    "PAN": "Panama",    "PER": "Peru",      "PNG": "Papua New Guinea",
    "PHL": "Philippines", "POL": "Poland",  "PRT": "Portugal",
    "RUS": "Russia",    "SAU": "Saudi Arabia", "SWE": "Sweden",
    "SEN": "Senegal",   "THA": "Thailand",  "TUN": "Tunisia",
    "TUR": "Turkey",    "TWN": "Taiwan",    "TZA": "Tanzania",
    "URY": "Uruguay",   "USA": "United States", "VNM": "Viet Nam",
    "ZAF": "South Africa",
}

# Playwright is heavy; cap concurrent country crawls so a parallel pipeline
# doesn't fork too many chromiums at once and OOM the box. Two is enough to
# overlap two countries while leaving GPU headroom for the gemma3 summaries.
_PLAYWRIGHT_SEM = BoundedSemaphore(2)
_DETAIL_RENDER_CONCURRENCY = 5  # parallel detail-page renders within one browser
_SUMMARY_CONCURRENCY = 4        # matches Ollama's default OLLAMA_NUM_PARALLEL


# ── Cache (per-country JSON) ──────────────────────────────────────────────


def _country_cache_path(iso3: str) -> Path:
    return CACHE_DIR / f"{iso3.upper()}.json"


def _read_country_cache(
    iso3: str, subject: str, search: str, ttl: int
) -> dict[str, Any] | None:
    """Return cached payload iff it matches (iso3, subject, search) and is fresh."""
    path = _country_cache_path(iso3)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("subject") != subject or data.get("search") != search:
        return None
    if (time.time() - data.get("cached_at", 0)) > ttl:
        return None
    return data


def _write_country_cache(payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    iso3 = payload["iso3"].upper()
    _country_cache_path(iso3).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Search-results parsing ────────────────────────────────────────────────


def _build_search_url(iso3: str, subject: str, search: str) -> str:
    qs = f"search={search}&yearFrom=&yearTo=&endstring=1"
    frag = base64.b64encode(qs.encode("utf-8")).decode("ascii")
    return (
        f"https://www.fao.org/faolex/results/en/?country={iso3.upper()}"
        f"&subject={subject}#querystring={frag}"
    )


def _strip(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s or None


def _parse_records(rendered_text: str, max_records: int) -> list[dict[str, Any]]:
    """Linear scan over the rendered SPA text, anchored on `FAOLEX No:`.

    Single-pass-ish (two passes in the same function) — avoids the
    catastrophic-backtracking we saw with a nested-quantifier regex over
    long abstracts.
    """
    lines = [ln.rstrip() for ln in rendered_text.splitlines()]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    anchors: list[tuple[int, str, str | None, str | None, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == _NO_HEADER:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                break
            id_match = _LEX_ID_RE.match(lines[j].strip())
            if not id_match:
                i = j + 1
                continue
            rid = id_match.group(1)
            year = None
            rtype = None
            type_end = j
            k = j + 1
            steps = 0
            while k < len(lines) and steps < 8:
                line = lines[k].strip()
                if line == _YEAR_HEADER:
                    k += 1
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    if k < len(lines):
                        year = _strip(lines[k])
                        type_end = k
                elif line == _TYPE_HEADER:
                    k += 1
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    if k < len(lines):
                        rtype = _strip(lines[k])
                        type_end = k
                        break
                k += 1
                steps += 1
            anchors.append((i, rid, year, rtype, type_end))
            i = type_end + 1
        else:
            i += 1

    last_end = 0
    for anchor_idx, rid, year, rtype, type_end in anchors:
        if rid in seen or rid in _FAO_CHROME_IDS:
            last_end = type_end + 1
            continue
        seen.add(rid)
        block: list[str] = []
        for ln in lines[last_end:anchor_idx]:
            stripped = ln.strip()
            if not stripped or stripped in _FAO_CHROME_LINES:
                continue
            if any(stripped.startswith(pref) for pref in _FAO_CHROME_PREFIXES):
                continue
            block.append(stripped)
        last_end = type_end + 1

        title = None
        abstract_lines: list[str] = []
        for line in block:
            if title is None:
                title = line
                continue
            abstract_lines.append(line)
        if (
            title and abstract_lines
            and len(title) <= 32
            and "." not in title
            and len(abstract_lines[0]) > len(title)
        ):
            title = abstract_lines.pop(0)
        abstract = " ".join(abstract_lines).strip()
        if len(abstract) > 600:
            abstract = abstract[:597] + "..."
        out.append({
            "id": rid,
            "title": _strip(title),
            "year": year,
            "type": rtype,
            "abstract": abstract or None,
            "detail_url": _DETAIL_URL.format(id=rid),
        })
        if len(out) >= max_records:
            break
    return out


# ── Browser session (one chromium for search + N details) ─────────────────


class _AsyncBrowserSession:
    """Reuse one Playwright browser/context across many concurrent renders.

    Async so the N detail-page fetches can be `asyncio.gather`'d on the
    same chromium instance. Caller is sync — see `_render_country` which
    drives this via `asyncio.run`.
    """

    def __init__(self, *, user_agent: str | None = None):
        self.user_agent = user_agent or (
            "overfished-iuu-pipeline/0.1 "
            "(research; +https://github.com/overfished)"
        )
        self._pw_cm = None
        self.browser = None
        self.ctx = None

    async def __aenter__(self) -> "_AsyncBrowserSession":
        from playwright.async_api import async_playwright

        self._pw_cm = async_playwright()
        pw = await self._pw_cm.__aenter__()
        self.browser = await pw.chromium.launch(headless=True)
        self.ctx = await self.browser.new_context(user_agent=self.user_agent)
        return self

    async def render(
        self, url: str, *, timeout_ms: int = 60000, settle_ms: int = 2000
    ) -> str | None:
        if self.ctx is None:
            return None
        page = await self.ctx.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            # SPA renders results from XHR after networkidle on some runs —
            # give it a beat to populate the DOM.
            await page.wait_for_timeout(settle_ms)
            main = await page.query_selector("main") or await page.query_selector("body")
            if main is None:
                return None
            return await main.inner_text()
        except Exception:
            return None
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self.browser is not None:
                await self.browser.close()
        finally:
            if self._pw_cm is not None:
                await self._pw_cm.__aexit__(exc_type, exc, tb)


async def _render_country(
    search_url: str, *, max_records: int
) -> tuple[list[dict[str, Any]], bool]:
    """Render the search SPA + every detail page in one chromium.

    Detail renders are gathered concurrently behind a Semaphore so the
    browser doesn't open more than _DETAIL_RENDER_CONCURRENCY pages at a
    time. Returns (records, rendered_search).
    """
    async with _AsyncBrowserSession() as sess:
        search_text = await sess.render(search_url, settle_ms=2500)
        if search_text is None:
            return [], False
        records = _parse_records(search_text, max_records=max_records)

        sem = asyncio.Semaphore(_DETAIL_RENDER_CONCURRENCY)

        async def _fetch_detail(rec: dict[str, Any]) -> None:
            async with sem:
                detail_text = await sess.render(rec["detail_url"], settle_ms=1500)
            if detail_text:
                cleaned = _clean_detail_text(detail_text)
                rec["full_text"] = cleaned[:DETAIL_TEXT_CACHE_CHARS] or None
            else:
                rec["full_text"] = None

        if records:
            await asyncio.gather(*(_fetch_detail(rec) for rec in records))
        return records, True


def _clean_detail_text(text: str) -> str:
    """Drop the SPA chrome from a detail-page render so the LLM sees the law."""
    lines = [
        ln for ln in (l.strip() for l in text.splitlines())
        if ln and ln not in _FAO_CHROME_LINES
        and not any(ln.startswith(p) for p in _FAO_CHROME_PREFIXES)
    ]
    return "\n".join(lines)


# ── LLM summarizer (gemma3:4b plain generation, no tools) ─────────────────


_SECTION_RE = re.compile(
    r"^(?P<header>PROHIBITIONS|GEAR_RESTRICTIONS|AREA_RESTRICTIONS|"
    r"PENALTY_SUMMARY|FOREIGN_VESSELS_APPLY|IUU_RELEVANT|CITATION_QUOTE)\s*:",
    re.MULTILINE,
)


def _parse_summary_response(text: str) -> dict[str, Any]:
    """Walk the gemma3 output line-by-line into a structured dict.

    The prompt asks for fixed section headers; this is more reliable than
    asking gemma3 for JSON, which a 4B model sometimes mangles.
    """
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for raw in text.splitlines():
        m = _SECTION_RE.match(raw)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group("header")
            buf = [raw[m.end():].strip()]
        elif current is not None:
            buf.append(raw)
    if current is not None:
        sections[current] = "\n".join(buf).strip()

    def _normalize(line: str) -> str:
        """Drop markdown bold/italic and leading bullet markers."""
        line = line.strip()
        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^[*_]+|[*_]+$", "", line.strip())
        return line.strip()

    def _bullets(s: str) -> list[str]:
        out: list[str] = []
        for ln in (s or "").splitlines():
            cleaned = _normalize(ln)
            if not cleaned or cleaned.lower() == "(none)":
                continue
            out.append(cleaned)
        return out

    def _single(s: str) -> str | None:
        """Single-value field — gemma3 sometimes emits a bullet or markdown.

        Join non-empty lines, strip leading bullet/markdown wrappers, then
        return None for an empty / "(none)" value.
        """
        joined = " ".join(_normalize(ln) for ln in (s or "").splitlines() if ln.strip())
        joined = joined.strip()
        if not joined or joined.lower() == "(none)":
            return None
        return joined

    def _yesno(s: str) -> str | None:
        # Find the first "yes"/"no"/"unclear" token anywhere in the value,
        # ignoring markdown markers, bullets, or trailing punctuation.
        cleaned = re.sub(r"[*_`]+", "", (s or "")).lower()
        m = re.search(r"\b(yes|no|unclear)\b", cleaned)
        return m.group(1) if m else None

    return {
        "prohibitions": _bullets(sections.get("PROHIBITIONS", "")),
        "gear_restrictions": _bullets(sections.get("GEAR_RESTRICTIONS", "")),
        "area_restrictions": _bullets(sections.get("AREA_RESTRICTIONS", "")),
        "penalty_summary": _single(sections.get("PENALTY_SUMMARY", "")),
        "foreign_vessels_apply": _yesno(sections.get("FOREIGN_VESSELS_APPLY", "")),
        "iuu_relevant": _yesno(sections.get("IUU_RELEVANT", "")),
        "citation_quote": _single(sections.get("CITATION_QUOTE", "")),
    }


def _summarize_law(
    full_text: str, *, title: str | None, year: str | None, rtype: str | None
) -> dict[str, Any] | None:
    """Run gemma3:4b over the statute text and parse the structured response.

    Returns None if the LLM call fails (e.g. Ollama unreachable). The crawler
    keeps the record without a summary in that case — better than dropping
    the record entirely.
    """
    if not full_text:
        return None

    snippet = full_text[:DETAIL_TEXT_TRIM_CHARS]
    if len(full_text) > DETAIL_TEXT_TRIM_CHARS:
        snippet = snippet + "\n[...truncated...]"

    prompt = (
        "You are a fisheries-law analyst. Read the following law and emit a "
        "structured summary using the EXACT section headers below — no extra "
        "commentary, no JSON, no markdown. Use \"(none)\" when the law does "
        "not address a section.\n\n"
        "LAW METADATA:\n"
        f"- Title: {title or '(unknown)'}\n"
        f"- Year: {year or '(unknown)'}\n"
        f"- Type: {rtype or '(unknown)'}\n\n"
        "LAW TEXT:\n"
        f"{snippet}\n\n"
        "OUTPUT (use these headers exactly, one bullet per item):\n\n"
        "PROHIBITIONS:\n"
        "- <prohibition or \"(none)\">\n\n"
        "GEAR_RESTRICTIONS:\n"
        "- <restriction or \"(none)\">\n\n"
        "AREA_RESTRICTIONS:\n"
        "- <restriction or \"(none)\">\n\n"
        "PENALTY_SUMMARY:\n"
        "<one sentence covering fines / imprisonment / forfeiture, or \"(none)\">\n\n"
        "FOREIGN_VESSELS_APPLY: <yes / no / unclear>\n\n"
        "IUU_RELEVANT: <yes / no>\n\n"
        "CITATION_QUOTE:\n"
        "<one short clause from the law that captures its key rule, or \"(none)\">"
    )

    try:
        from services.llm import build_chat_llm

        llm = build_chat_llm("light", num_predict=768)
        response = llm.invoke(prompt)
        body = response.content if hasattr(response, "content") else str(response)
        if isinstance(body, list):
            # ChatOllama can return a list of content blocks; flatten.
            body = "".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in body
            )
        return _parse_summary_response(body)
    except Exception:
        return None


# ── Top-level entry point ─────────────────────────────────────────────────


def crawl_faolex_records(
    iso3: str,
    *,
    subject: str = "Fisheries",
    search: str | None = None,
    max_records: int = RECORDS_CAP,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    use_cache: bool = True,
    summarize: bool = True,
) -> dict[str, Any]:
    """Render FAOLEX → fetch detail pages → summarize via gemma3 → cache.

    Returns:
      {
        "iso3": "THA",
        "subject": "Fisheries",
        "search": "Thailand fisheries",
        "search_url": "https://...#querystring=<base64>",
        "records": [
          {
            "id", "title", "year", "type", "abstract", "detail_url",
            "full_text" (str | None),
            "summary"   (dict | None),
          }
        ],
        "rendered": True if Playwright produced search results,
        "cached":   True if the whole payload came from disk,
        "summarized_count": <int>,
        "checked_at": "<iso8601>",
      }

    Pass summarize=False to skip gemma3 (only fetch search + detail text);
    useful for batch pre-warming when the LLM isn't available.
    """
    iso3 = iso3.upper()
    if not search:
        country_name = _ISO3_TO_NAME.get(iso3, iso3)
        search = f"{country_name} {subject.lower()}"
    search_url = _build_search_url(iso3, subject, search)

    if use_cache:
        cached = _read_country_cache(iso3, subject, search, ttl_seconds)
        if cached is not None:
            cached["cached"] = True
            cached["checked_at"] = datetime.now(timezone.utc).isoformat()
            return cached

    # Heavy work: launch one chromium, render search + every detail page
    # concurrently (asyncio inside _render_country). The semaphore caps
    # us at 2 simultaneous country crawls process-wide.
    records: list[dict[str, Any]] = []
    rendered = False
    with _PLAYWRIGHT_SEM:
        try:
            records, rendered = asyncio.run(
                _render_country(search_url, max_records=max_records)
            )
        except Exception:
            return _failed_payload(iso3, subject, search, search_url,
                                   reason="browser_session_failed",
                                   partial=records, rendered=rendered)
        if not rendered:
            return _failed_payload(iso3, subject, search, search_url,
                                   reason="search_render_failed")

    # Default summaries to None; the executor below fills them in for
    # records that actually got full_text.
    for rec in records:
        rec["summary"] = None

    summarized = 0
    if summarize:
        fillable = [r for r in records if r.get("full_text")]
        if fillable:
            with ThreadPoolExecutor(max_workers=_SUMMARY_CONCURRENCY) as ex:
                futures = {
                    ex.submit(
                        _summarize_law,
                        r["full_text"],
                        title=r.get("title"),
                        year=r.get("year"),
                        rtype=r.get("type"),
                    ): r
                    for r in fillable
                }
                for fut in as_completed(futures):
                    rec = futures[fut]
                    try:
                        summary = fut.result()
                    except Exception:
                        summary = None
                    rec["summary"] = summary
                    if summary is not None:
                        summarized += 1

    payload = {
        "iso3": iso3,
        "subject": subject,
        "search": search,
        "search_url": search_url,
        "records": records,
        "rendered": rendered,
        "cached": False,
        "summarized_count": summarized,
        "cached_at": time.time(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if records:
        _write_country_cache(payload)
    return payload


def _failed_payload(
    iso3: str, subject: str, search: str, search_url: str,
    *, reason: str, partial: list | None = None, rendered: bool = False,
) -> dict[str, Any]:
    return {
        "iso3": iso3,
        "subject": subject,
        "search": search,
        "search_url": search_url,
        "records": partial or [],
        "rendered": rendered,
        "cached": False,
        "summarized_count": 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": reason,
    }
