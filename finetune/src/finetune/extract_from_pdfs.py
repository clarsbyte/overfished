"""Extract structured rule tuples directly from PDF files.

Reads every .pdf from a source directory, maps filenames to ISO-3 country
codes, extracts plain text via pypdf, then applies the same stub extractor
used by extract_corpus.py.

Usage:
    python -m finetune.extract_from_pdfs
    python -m finetune.extract_from_pdfs --pdf-dir C:/Users/Clarissa/Downloads/fish-law
    python -m finetune.extract_from_pdfs --pdf-dir /path/to/pdfs --out data/my_rules.jsonl --append

Writes:
    finetune/data/extracted_rules.jsonl  (same format as extract_corpus.py output)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    import pypdf
except ImportError:
    raise SystemExit(
        "pypdf is required: pip install pypdf\n"
        "Or add it to pyproject.toml and reinstall."
    )

from finetune.extract_corpus import extract_rules_stub, OUT_PATH

# Maps the base filename (lowercased, trailing _N stripped) to ISO-3.
FILENAME_TO_ISO3: dict[str, str] = {
    "australia": "AUS",
    "china": "CHN",
    "indonesia": "IDN",
    "ireland": "IRL",
    "japan": "JPN",
    "korea": "KOR",
    "laos": "LAO",
    "latvia": "LVA",
    "philippines": "PHL",
    "poland": "POL",
    "south_africa": "ZAF",
    "south_korea": "KOR",
    "united_kingdom": "GBR",
    "united_states": "USA",
}

_SUFFIX_RE = re.compile(r"_\d+$")


def _iso3_from_path(pdf_path: Path) -> str:
    stem = pdf_path.stem.lower()
    base = _SUFFIX_RE.sub("", stem)
    return FILENAME_TO_ISO3.get(base, base.upper()[:3])


def _extract_text(pdf_path: Path) -> str:
    reader = pypdf.PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text)
    return "\n".join(pages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract rule tuples from local PDF files.")
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path(__file__).resolve().parents[4] / "Downloads" / "fish-law",
        help="Directory containing .pdf files (default: ~/Downloads/fish-law relative to repo).",
    )
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing output file instead of overwriting.",
    )
    args = parser.parse_args()

    pdf_files = sorted(args.pdf_dir.glob("*.pdf"))
    if not pdf_files:
        raise SystemExit(f"No PDF files found in {args.pdf_dir}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"
    total = 0

    with args.out.open(mode, encoding="utf-8") as out_f:
        for pdf_path in pdf_files:
            iso3 = _iso3_from_path(pdf_path)
            print(f"  [{iso3}] {pdf_path.name} — extracting text…", end=" ", flush=True)

            text = _extract_text(pdf_path)
            if not text.strip():
                print("(empty, skipped)")
                continue

            rules = extract_rules_stub(
                text,
                country=iso3,
                source_doc=pdf_path.stem,
                source_url="",
            )

            for rule in rules:
                out_f.write(json.dumps(rule, ensure_ascii=False) + "\n")

            total += len(rules)
            print(f"{len(rules)} rule(s)")

    print(f"\nWrote {total} total rule(s) to {args.out}")


if __name__ == "__main__":
    main()
