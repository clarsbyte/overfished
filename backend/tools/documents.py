"""Legal-document generator — thin wrapper over ``documents/render.py``.

Always-runs (no fixture branch); the renderer is the demo. Both functions are
synchronous wrappers that drive the async Playwright pipeline.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from documents.render import render_document_family as _render_family
from documents.render import render_one_document as _render_one
from tools.schemas import CaseFile, DocumentArtifact

DocType = Literal[
    "notice_of_violation",
    "cease_and_desist_order",
    "port_inspection_order",
    "evidence_package",
]


def render_document(case: CaseFile, doc_type: DocType) -> DocumentArtifact:
    """Render a single document from a CaseFile (sync wrapper around Playwright)."""
    return asyncio.run(_render_one(case, doc_type))


def render_full_document_family(case: CaseFile) -> list[DocumentArtifact]:
    """Render all four documents from a single CaseFile."""
    return asyncio.run(_render_family(case))
