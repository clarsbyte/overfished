"""Async FAOLEX scraper with multi-tier fallback.

FAOLEX (https://www.fao.org/faolex/) is Drupal + JS-rendered: the search
results page returns an empty shell. The reliable path is the detail URL
pattern when a record ID is known:

    https://www.fao.org/faolex/results/details/en/c/<LEX-FAOC-XXXXXXX>/

Strategy per country, in order until something returns content:

  1. SEARCH    — hit the country/topic search URL, scrape LEX-FAOC IDs out
                  of whatever HTML the server emits (often nothing if JS).
  2. SEEDS     — fall back to finetune/data/seeds/<iso3>.json, a list of
                  known IDs maintained by hand or a previous run.
  3. RENDER    — `--render` enables playwright for JS-rendered pages
                  (opt-in; needs the `[render]` extra installed).
  4. MIRROR    — finetune/data/raw/<iso3>/manual/*.html is parsed if
                  network paths fail entirely.

Each successful fetch persists:
    finetune/data/raw/<iso3>/<id>.html      raw page (for re-parsing)
    finetune/data/raw/<iso3>/<id>.json      structured: id, country, title,
                                            year, abstract, text, url

Cached aggressively: presence of <id>.json skips the fetch unless --force.

CLI:
    python -m finetune.fetch_faolex --countries ECU PHL ESP CHN IDN --max 20
    python -m finetune.fetch_faolex --countries ECU --max 3
    python -m finetune.fetch_faolex --countries ECU --render
    python -m finetune.fetch_faolex --parse-mirror      # parse manual HTML only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import httpx
from bs4 import BeautifulSoup

DEMO_COUNTRIES = ["ECU", "PHL", "ESP", "CHN", "IDN"]
SEARCH_URL = "https://www.fao.org/faolex/results/en/"
DETAIL_URL = "https://www.fao.org/faolex/results/details/en/c/{id}/"
USER_AGENT = (
    "OverfishedResearchBot/0.1 (academic; +https://github.com/overfished) "
    "httpx"
)
LEX_PATTERN = re.compile(r"LEX-FAO[CS][- ]?\d{5,8}", re.IGNORECASE)

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
SEEDS_DIR = ROOT / "data" / "seeds"


@dataclass
class FaolexRecord:
    id: str
    country: str
    title: str
    year: int | None
    abstract: str
    text: str
    url: str
    source: str  # "search" | "seeds" | "render" | "mirror"


def _normalize_id(raw: str) -> str:
    return raw.replace(" ", "-").upper()


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        r = await client.get(url, timeout=20.0, follow_redirects=True)
        if r.status_code != 200 or not r.text:
            return None
        return r
    except (httpx.HTTPError, httpx.TimeoutException):
        return None


async def discover_ids_via_search(
    client: httpx.AsyncClient, iso3: str, max_n: int
) -> list[str]:
    """Best-effort: extract LEX-FAOC IDs from the search results HTML."""
    params = {"country": iso3, "subject": "Fisheries"}
    r = await _get(client, f"{SEARCH_URL}?{httpx.QueryParams(params)}")
    if r is None:
        return []
    found = list({_normalize_id(m.group(0)) for m in LEX_PATTERN.finditer(r.text)})
    return found[:max_n]


def load_seed_ids(iso3: str, max_n: int) -> list[str]:
    path = SEEDS_DIR / f"{iso3}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    ids: list[str] = []
    for item in data:
        if isinstance(item, str):
            ids.append(_normalize_id(item))
        elif isinstance(item, dict) and "id" in item:
            ids.append(_normalize_id(item["id"]))
    return ids[:max_n]


def parse_detail_html(html: str, faolex_id: str, iso3: str, source: str) -> FaolexRecord | None:
    """Extract title, year, abstract, text from a FAOLEX detail page.

    The detail-page DOM is inconsistent across countries; we look for the
    most-stable signals (the document title, any year between 1950-2030 in
    the metadata block, and concatenate the largest text container).
    """
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.find(["h1", "h2"]) or soup.find("title")
    title = title_el.get_text(" ", strip=True) if title_el else ""

    year: int | None = None
    for m in re.finditer(r"\b(19\d{2}|20[0-2]\d)\b", html):
        candidate = int(m.group(0))
        if 1950 <= candidate <= 2030:
            year = candidate
            break

    abstract = ""
    abstract_el = soup.find(string=re.compile(r"abstract", re.IGNORECASE))
    if abstract_el and abstract_el.parent:
        sibling = abstract_el.parent.find_next(["p", "div"])
        if sibling:
            abstract = sibling.get_text(" ", strip=True)

    candidates = soup.find_all(["main", "article", "div"], recursive=True)
    body_text = ""
    for el in candidates:
        text = el.get_text("\n", strip=True)
        if len(text) > len(body_text):
            body_text = text
    if not body_text:
        body_text = soup.get_text("\n", strip=True)

    if not title and not body_text:
        return None

    return FaolexRecord(
        id=faolex_id,
        country=iso3,
        title=title or faolex_id,
        year=year,
        abstract=abstract,
        text=body_text,
        url=DETAIL_URL.format(id=faolex_id),
        source=source,
    )


async def fetch_record(
    client: httpx.AsyncClient,
    faolex_id: str,
    iso3: str,
    source: str,
    *,
    semaphore: asyncio.Semaphore,
    pacing_seconds: float = 1.0,
    force: bool = False,
) -> FaolexRecord | None:
    out_dir = RAW_DIR / iso3
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{faolex_id}.json"
    html_path = out_dir / f"{faolex_id}.html"

    if json_path.exists() and not force:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return FaolexRecord(**data)
        except (json.JSONDecodeError, TypeError):
            pass

    url = DETAIL_URL.format(id=faolex_id)
    async with semaphore:
        await asyncio.sleep(pacing_seconds)
        r = await _get(client, url)
    if r is None:
        return None

    html_path.write_text(r.text, encoding="utf-8")
    record = parse_detail_html(r.text, faolex_id, iso3, source)
    if record is None:
        return None
    json_path.write_text(json.dumps(asdict(record), indent=2, ensure_ascii=False), encoding="utf-8")
    return record


async def render_record(faolex_id: str, iso3: str) -> FaolexRecord | None:
    """Playwright fallback for JS-rendered detail pages."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"  [render] playwright not installed; install with `pip install -e .[render]`")
        return None

    out_dir = RAW_DIR / iso3
    out_dir.mkdir(parents=True, exist_ok=True)
    url = DETAIL_URL.format(id=faolex_id)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT)
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
        except Exception as exc:
            print(f"  [render] {faolex_id} failed: {exc!s}")
            await browser.close()
            return None
        await browser.close()

    (out_dir / f"{faolex_id}.html").write_text(html, encoding="utf-8")
    record = parse_detail_html(html, faolex_id, iso3, source="render")
    if record:
        (out_dir / f"{faolex_id}.json").write_text(
            json.dumps(asdict(record), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return record


def parse_manual_mirror(iso3: str) -> list[FaolexRecord]:
    """Parse hand-mirrored HTML files in data/raw/<iso3>/manual/*.html."""
    manual_dir = RAW_DIR / iso3 / "manual"
    if not manual_dir.exists():
        return []
    out: list[FaolexRecord] = []
    for html_file in manual_dir.glob("*.html"):
        faolex_id = _normalize_id(html_file.stem)
        record = parse_detail_html(html_file.read_text(encoding="utf-8"), faolex_id, iso3, source="mirror")
        if record:
            (RAW_DIR / iso3 / f"{faolex_id}.json").write_text(
                json.dumps(asdict(record), indent=2, ensure_ascii=False), encoding="utf-8"
            )
            out.append(record)
    return out


async def fetch_country(
    client: httpx.AsyncClient,
    iso3: str,
    max_n: int,
    *,
    use_search: bool,
    use_render: bool,
    force: bool,
) -> list[FaolexRecord]:
    semaphore = asyncio.Semaphore(4)
    results: dict[str, FaolexRecord] = {}

    discovered: list[str] = []
    if use_search:
        discovered = await discover_ids_via_search(client, iso3, max_n)
        print(f"[{iso3}] search: discovered {len(discovered)} ID(s) in shell HTML")

    seeds = load_seed_ids(iso3, max_n)
    print(f"[{iso3}] seeds: {len(seeds)} ID(s) from data/seeds/{iso3}.json")

    candidate_ids: list[str] = []
    for x in discovered + seeds:
        if x not in candidate_ids:
            candidate_ids.append(x)
    candidate_ids = candidate_ids[:max_n]

    if not candidate_ids:
        print(f"[{iso3}] no IDs available — checking manual mirror")
        results_mirror = parse_manual_mirror(iso3)
        print(f"[{iso3}] mirror: parsed {len(results_mirror)} record(s)")
        return results_mirror

    tasks = [
        fetch_record(client, fid, iso3, source="search" if fid in discovered else "seeds",
                     semaphore=semaphore, force=force)
        for fid in candidate_ids
    ]
    for fid, record in zip(candidate_ids, await asyncio.gather(*tasks)):
        if record:
            results[fid] = record

    if use_render:
        missing = [fid for fid in candidate_ids if fid not in results]
        for fid in missing:
            record = await render_record(fid, iso3)
            if record:
                results[fid] = record

    mirror = parse_manual_mirror(iso3)
    for record in mirror:
        results.setdefault(record.id, record)

    print(f"[{iso3}] total persisted: {len(results)} record(s)")
    return list(results.values())


async def fetch_all(
    countries: Iterable[str],
    max_n: int,
    *,
    use_search: bool = True,
    use_render: bool = False,
    force: bool = False,
) -> dict[str, list[FaolexRecord]]:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
    async with httpx.AsyncClient(headers=headers) as client:
        out: dict[str, list[FaolexRecord]] = {}
        for iso3 in countries:
            out[iso3] = await fetch_country(
                client, iso3, max_n,
                use_search=use_search, use_render=use_render, force=force,
            )
        return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch FAOLEX fisheries documents.")
    parser.add_argument(
        "--countries", nargs="+", default=DEMO_COUNTRIES,
        help="ISO3 country codes (default: ECU PHL ESP CHN IDN)",
    )
    parser.add_argument("--max", type=int, default=20, help="max records per country")
    parser.add_argument("--render", action="store_true", help="enable playwright fallback")
    parser.add_argument("--force", action="store_true", help="re-fetch even if cached")
    parser.add_argument(
        "--no-search", action="store_true",
        help="skip the (often empty) search step; go straight to seeds",
    )
    parser.add_argument(
        "--parse-mirror", action="store_true",
        help="only parse data/raw/<iso3>/manual/*.html — no network",
    )
    args = parser.parse_args()

    if args.parse_mirror:
        for iso3 in args.countries:
            records = parse_manual_mirror(iso3)
            print(f"[{iso3}] mirror: {len(records)} record(s)")
        return

    summary = asyncio.run(
        fetch_all(
            args.countries, args.max,
            use_search=not args.no_search,
            use_render=args.render,
            force=args.force,
        )
    )
    total = sum(len(v) for v in summary.values())
    print(f"\nDone. {total} record(s) across {len(summary)} country/countries.")


if __name__ == "__main__":
    main()
