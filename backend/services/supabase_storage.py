"""Upload rendered evidence PDFs to Supabase Storage (bucket: evidence).

Path convention inside the bucket:
    <case_id>/combined_legal_package.pdf

Usage:
    from services.supabase_storage import upload_evidence_pdf
    public_url = upload_evidence_pdf(case_id, pdf_path)
"""

from __future__ import annotations

import os
from pathlib import Path


def _client():
    from supabase import create_client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    return create_client(url, key)


def upload_evidence_pdf(
    case_id: str,
    pdf_path: Path | str,
    bucket: str | None = None,
) -> str:
    """Upload a PDF to Supabase Storage and return its public URL.

    Args:
        case_id: Folder name inside the bucket (e.g. "Galapagos_IUU_20260425").
        pdf_path: Local path to the PDF file.
        bucket: Storage bucket name. Defaults to SUPABASE_EVIDENCE_BUCKET env var.

    Returns:
        Public URL of the uploaded file.
    """
    bucket_name = bucket or os.getenv("SUPABASE_EVIDENCE_BUCKET", "evidence")
    pdf_path = Path(pdf_path)
    storage_path = f"{case_id}/{pdf_path.name}"

    client = _client()
    with open(pdf_path, "rb") as f:
        data = f.read()

    # upsert=True overwrites if a previous run already uploaded this case.
    client.storage.from_(bucket_name).upload(
        path=storage_path,
        file=data,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )

    url_response = client.storage.from_(bucket_name).get_public_url(storage_path)
    return url_response
