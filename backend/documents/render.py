"""Jinja2 → Playwright HTML/PDF renderer with SHA-256 anchoring.

Pipeline per document:
  1. Render HTML with ``sha256_placeholder = "0" * 64``.
  2. SHA-256 the canonical HTML bytes (without the placeholder hash).
  3. Re-render HTML with that hash baked into the footer; save as ``.html``.
  4. PDF the final HTML.

Why hash the HTML and not the PDF: the embedded footer hash needs a fixed-point.
Hashing PDF bytes that contain the hash is circular (changing the hash changes
the bytes, which changes the hash). Hashing the canonical HTML — the same
artifact that renders the PDF — gives a stable value that verifies via
``shasum -a 256 file.html``. The PDF is a derived view; the HTML is the
authoritative artifact, which is consistent with how real legal docs treat
machine-readable filings.

Direct invocation::

    python -m documents.render

renders the four-document family for the demo CaseFile into
``backend/output/IUU-2026-001847/``.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import Browser, async_playwright

from tools.schemas import CaseFile, DocumentArtifact

DocType = Literal[
    "notice_of_violation",
    "cease_and_desist_order",
    "port_inspection_order",
    "evidence_package",
    "combined_legal_package",
]

TEMPLATES_DIR = Path(__file__).parent / "templates"
ASSETS_DIR = Path(__file__).parent / "assets"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

PLACEHOLDER_HASH = "0" * 64

# Map DocType → (template filename, doc_title for <title>).
# Page count is read from the rendered PDF, not declared up-front.
_DOC_META: dict[str, dict] = {
    "notice_of_violation": {
        "template": "notice_of_violation.html",
        "title": "Notice of Violation",
    },
    "cease_and_desist_order": {
        "template": "cease_and_desist.html",
        "title": "Cease and Desist Order",
    },
    "port_inspection_order": {
        "template": "port_inspection_order.html",
        "title": "Port State Inspection Order",
    },
    "evidence_package": {
        "template": "evidence_package.html",
        "title": "Evidence Package",
    },
    "combined_legal_package": {
        "template": "combined_legal_package.html",
        "title": "Combined Legal Package",
    },
}


def _env() -> Environment:
    """Jinja env with two search roots: ``templates/`` and ``documents/`` itself.

    Bare names like ``notice_of_violation.html`` and ``_base.html`` resolve from
    ``templates/``. Path-prefixed names like ``assets/seal.svg`` resolve from
    ``documents/``. Autoescape is turned off for SVG/CSS fragments (they're
    trusted, hand-authored assets).
    """
    return Environment(
        loader=FileSystemLoader([str(TEMPLATES_DIR), str(Path(__file__).parent)]),
        autoescape=select_autoescape(disabled_extensions=("html", "svg", "css"), default=False),
        keep_trailing_newline=True,
    )


def _decimal_to_dms(coord: float, axis: Literal["lat", "lon"]) -> str:
    """Convert a signed decimal coordinate to DMS string with hemisphere suffix."""
    hemi = ("S" if axis == "lat" else "W") if coord < 0 else ("N" if axis == "lat" else "E")
    abs_v = abs(coord)
    deg = int(abs_v)
    minutes_full = (abs_v - deg) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    return f"{deg}°{minutes:02d}′{int(round(seconds)):02d}″{hemi}"


def _build_context(case: CaseFile, doc_type: DocType, sha256: str) -> dict:
    """Common context for all four templates."""
    meta = _DOC_META[doc_type]
    last = case.vessel.last_position
    last_dms = (
        f"{_decimal_to_dms(last.lat, 'lat')}, {_decimal_to_dms(last.lon, 'lon')}"
        if last
        else None
    )
    last_seen_human = (
        case.vessel.last_seen.strftime("%Y-%m-%d %H:%M UTC")
        if case.vessel.last_seen
        else None
    )

    findings = _findings_for(case)
    violations_cited = [
        {"instrument": c.instrument, "role_text": _role_text(c)} for c in (case.citations or [])
    ]

    # Pick the predicted port for the port_inspection_order
    port_ctx: dict = {}
    if doc_type == "port_inspection_order":
        port_ctx = {
            "name": "Port of Manta",
            "un_locode": "EC MEC",
            "country": "ECU",
            "country_full": "Ecuador",
        }

    flag_full = {
        "CHN": "People's Republic of China",
        "ECU": "Republic of Ecuador",
        "PER": "Republic of Peru",
        "KOR": "Republic of Korea",
        "ESP": "Spain",
        "PAN": "Republic of Panama",
    }.get(case.vessel.flag or "", case.vessel.flag or "")

    return {
        "case": case,
        "doc_title": meta["title"],
        "page_number": 1,
        "page_total": 1,  # placeholder; the PDF renderer paginates beyond this
        "doc_version": "1.0",
        "sha256_placeholder": sha256,
        "agency": {},  # use template defaults
        "ref": {
            "file_reference": f"GAL-MR-26-{case.case_id.split('-')[-1][-4:]}",
            "issued": "2026-04-24",
            "place": "Puerto Ayora, EC",
            "classification": "Civil — Tier II",
        },
        "signatory": {
            "script_name": "Luis A. Sandoval",
            "full_name": "Dr. Luis A. Sandoval, M.Sc.",
            "title": "Director, Marine Enforcement Unit",
            "agency": "Galápagos National Park Directorate",
            "issued_iso": "2026-04-24 · 14:18 UTC",
            "location": "Puerto Ayora, Galápagos, Ecuador",
        },
        "footer": {},
        # Derived fields
        "last_position_dms": last_dms,
        "last_seen_human": last_seen_human,
        "flag_full_name": flag_full,
        "findings": findings,
        "violations_cited": violations_cited,
        "port": port_ctx,
        "predicted_eta_human": "approximately 36 hours from issuance",
        "response_deadline": "24 May 2026",
        "acknowledge_deadline": "19 April 2026, 11:27 UTC",
        # Stamp parameterization
        "stamp_case_number": case.case_id.split("-")[-1] if "-" in case.case_id else case.case_id,
        "stamp_top_text": "APPROVED &nbsp;·&nbsp; ENFORCEMENT",
        "stamp_bottom_text": "2026-04-24 · GAL-MR",
    }


def _role_text(c) -> str:
    """Map a citation role to a short human description used in the operative sub-list."""
    return {
        "authority": "coastal-state enforcement and port-state action",
        "penalty": "civil penalty for unauthorized fishing within a protected marine area",
        "operational": "operational rule (vessel registry, AIS continuity)",
        "definitional": "definitional anchor for IUU fishing activity",
    }.get(c.role, c.role)


def _findings_for(case: CaseFile) -> list[str]:
    """Render the WHEREAS findings as HTML strings.

    For the demo vessel we emit the canonical seven findings (matching the
    reference HTML). For other vessels we fall back to a minimal structured
    list derived from events.
    """
    if case.vessel.mmsi == "412345678":
        return [
            (
                "on 18 April 2026 at <span class=\"mono\">03:42 UTC</span>, the Automatic "
                "Identification System (AIS) signal of fishing vessel <strong>"
                f"{case.vessel.name}</strong> (MMSI <span class=\"mono\">{case.vessel.mmsi}</span>) "
                "was last received at coordinates <span class=\"mono\">1°32′18″S, 91°08′42″W</span>, "
                "approximately 4.2 nautical miles outside the western boundary of the "
                f"{case.region.name};"
            ),
            (
                "AIS transmission resumed on 18 April 2026 at <span class=\"mono\">11:27 UTC</span> "
                "at coordinates <span class=\"mono\">0°45′12″S, 90°22′08″W</span>, indicating the "
                "vessel transited approximately 86 nautical miles within the boundaries of the "
                f"{case.region.name} over a period of <strong>7 hours, 45 minutes</strong> during "
                "which AIS transmission was disabled, in apparent contravention of "
                "<span class=\"cite\">SOLAS Chapter V, Regulation 19</span>;"
            ),
            (
                "Synthetic Aperture Radar (SAR) imagery acquired by the Sentinel-1A satellite on "
                "18 April 2026 at <span class=\"mono\">06:14 UTC</span> confirmed the presence of "
                "a vessel of dimensions consistent with the subject vessel (length 56±3 m) at "
                "coordinates <span class=\"mono\">1°08′04″S, 90°51′33″W</span>, well within the "
                f"boundaries of the {case.region.name} and within Zone 2.1 (no-take protected zone);"
            ),
            (
                "course and speed analysis during the period of AIS inactivity (mean speed "
                "<span class=\"mono\">3.4 kn</span>, course variance <span class=\"mono\">±48°</span>) "
                "is consistent with the deployment and retrieval of pelagic longline fishing gear, "
                "behaviour inconsistent with innocent passage as defined under "
                "<span class=\"cite\">UNCLOS Article 19</span>;"
            ),
            (
                "the subject vessel does not appear on the Authorized Vessel Register of the "
                "Galápagos National Park Directorate, the Inter-American Tropical Tuna Commission "
                "(IATTC) Regional Vessel Register (resolution C-19-01), or the Republic of "
                "Ecuador's authorization registry for foreign fishing vessels;"
            ),
            (
                "the Global Record of Fishing Vessels and the GFW Vessel Insights database indicate "
                "one (1) prior documented violation by the subject vessel: AIS-disabling event "
                "within the Peruvian EEZ on 03 September 2024, formally reported by the Peruvian "
                "Coast Guard;"
            ),
            (
                "the totality of the foregoing constitutes prima facie evidence of Illegal, "
                "Unreported, and Unregulated (IUU) fishing activity as defined under paragraph 3 "
                "of the <span class=\"cite\">FAO International Plan of Action to Prevent, Deter "
                "and Eliminate Illegal, Unreported and Unregulated Fishing (IPOA-IUU, 2001)</span>;"
            ),
        ]
    return [
        f"the subject vessel (MMSI <span class=\"mono\">{case.vessel.mmsi}</span>) was observed "
        f"operating within the {case.region.name};",
        "anomalous behaviour was identified by the system; full findings to follow.",
    ]


def _pdf_page_count(pdf_bytes: bytes) -> int:
    """Cheap PDF page-count via ``/Type /Page`` matches. Avoids a heavy dep."""
    import re

    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_bytes)) or 1


async def _render_pdf_bytes(env: Environment, browser: Browser, template_name: str, ctx: dict) -> bytes:
    template = env.get_template(template_name)
    html = template.render(**ctx)
    page = await browser.new_page()
    await page.set_content(html, wait_until="networkidle")
    pdf_bytes = await page.pdf(
        format="Letter",
        print_background=True,
        prefer_css_page_size=True,
        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
    )
    await page.close()
    return pdf_bytes


async def _render_html_string(env: Environment, template_name: str, ctx: dict) -> str:
    return env.get_template(template_name).render(**ctx)


async def render_one_document(case: CaseFile, doc_type: DocType, browser: Browser | None = None) -> DocumentArtifact:
    """Render a single document with HTML-anchored SHA-256."""
    meta = _DOC_META[doc_type]
    template_name = meta["template"]
    case_dir = OUTPUT_DIR / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    env = _env()

    own_browser = browser is None
    playwright = None
    if own_browser:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch()

    try:
        # Pass 1: canonical HTML with placeholder → hash that HTML.
        ctx = _build_context(case, doc_type, sha256=PLACEHOLDER_HASH)
        canonical_html = await _render_html_string(env, template_name, ctx)
        sha256 = hashlib.sha256(canonical_html.encode("utf-8")).hexdigest()

        # Pass 2: HTML with real hash → save that HTML and PDF it.
        ctx_final = _build_context(case, doc_type, sha256=sha256)
        final_html = await _render_html_string(env, template_name, ctx_final)
        final_pdf = await _render_pdf_bytes(env, browser, template_name, ctx_final)

        pdf_path = case_dir / f"{doc_type}.pdf"
        html_path = case_dir / f"{doc_type}.html"
        # Save canonical HTML (the authoritative pre-hash version) for verification:
        canonical_path = case_dir / f"{doc_type}.canonical.html"
        # write_bytes (not write_text) so Windows does not translate \n -> \r\n,
        # which would invalidate the SHA-256 anchor computed from canonical_html.
        canonical_path.write_bytes(canonical_html.encode("utf-8"))
        html_path.write_bytes(final_html.encode("utf-8"))
        pdf_path.write_bytes(final_pdf)
    finally:
        if own_browser:
            await browser.close()
            if playwright is not None:
                await playwright.stop()

    return DocumentArtifact(
        artifact_id=f"art-{case.case_id}-{doc_type}",
        case_id=case.case_id,
        doc_type=doc_type,
        html_url=f"/static/{case.case_id}/{doc_type}.html",
        pdf_url=f"/static/{case.case_id}/{doc_type}.pdf",
        sha256=sha256,
        rendered_at=datetime.now(timezone.utc),
        page_count=_pdf_page_count(final_pdf),
    )


async def render_document_family(case: CaseFile) -> list[DocumentArtifact]:
    """Render all four documents, sharing a single Chromium instance."""
    artifacts: list[DocumentArtifact] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for doc_type in (
                "notice_of_violation",
                "cease_and_desist_order",
                "port_inspection_order",
                "evidence_package",
            ):
                artifact = await render_one_document(case, doc_type, browser=browser)
                artifacts.append(artifact)
        finally:
            await browser.close()
    return artifacts


# ── CLI smoke test ──────────────────────────────────────────────────────


def _main() -> None:
    """Render the demo case to backend/output/<case_id>/ and print verifications."""
    from fixtures._loader import load_model

    case = load_model("case_galapagos_demo", CaseFile)
    artifacts = asyncio.run(render_document_family(case))

    print(f"\nRendered {len(artifacts)} documents to {OUTPUT_DIR / case.case_id}\n")
    for a in artifacts:
        case_dir = OUTPUT_DIR / case.case_id
        canonical = case_dir / f"{a.doc_type}.canonical.html"
        pdf_path = case_dir / f"{a.doc_type}.pdf"
        actual = hashlib.sha256(canonical.read_bytes()).hexdigest()
        ok = actual == a.sha256
        print(
            f"  {'✓' if ok else '✗'}  {a.doc_type:<25} sha256={a.sha256[:16]}…  "
            f"PDF {pdf_path.stat().st_size:>7} B  "
            f"{'canonical-html verified' if ok else 'MISMATCH'}"
        )


if __name__ == "__main__":
    _main()
