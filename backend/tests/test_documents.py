"""Smoke test for the document renderer.

Marked slow because each invocation spins up Chromium. We render only the
notice_of_violation document to keep the test under a few seconds; the full
four-document family is exercised by ``python -m documents.render``.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from documents.render import render_one_document, OUTPUT_DIR
from fixtures._loader import load_model
from tools.schemas import CaseFile


@pytest.mark.slow
def test_render_notice_of_violation_produces_valid_pdf_and_verifiable_hash():
    case = load_model("case_galapagos_demo", CaseFile)
    artifact = asyncio.run(render_one_document(case, "notice_of_violation"))

    case_dir: Path = OUTPUT_DIR / case.case_id
    pdf_path = case_dir / "notice_of_violation.pdf"
    canonical_path = case_dir / "notice_of_violation.canonical.html"
    final_html_path = case_dir / "notice_of_violation.html"

    assert pdf_path.exists() and pdf_path.stat().st_size > 100_000
    assert canonical_path.exists() and final_html_path.exists()

    # 1) The artifact's sha256 equals the SHA-256 of the canonical HTML bytes.
    canonical_hash = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    assert artifact.sha256 == canonical_hash

    # 2) The final HTML embeds the same hash.
    assert artifact.sha256 in final_html_path.read_text()

    # 3) PDF starts with the magic header.
    assert pdf_path.read_bytes().startswith(b"%PDF")

    # 4) Page count is at least 1.
    assert artifact.page_count >= 1
