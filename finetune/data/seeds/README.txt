FAOLEX seed lists (one JSON file per ISO3 country code).

Each file is a JSON array. Two formats are accepted:

  ["LEX-FAOC123456", "LEX-FAOC234567", ...]

or, with optional metadata:

  [
    {"id": "LEX-FAOC123456", "title": "Ley Orgánica de Pesca", "year": 2015},
    ...
  ]

These IDs feed fetch_faolex.py. Sourcing:

  1. Visit https://www.fao.org/faolex/results/en/?country=<ISO3>&subject=Fisheries
     (page is JS-rendered; let it load, then copy LEX-FAOC IDs from the URL bar
     when you click into a record).
  2. Or run `python -m finetune.fetch_faolex --countries <ISO3> --render` once
     to let playwright populate raw HTML, then copy IDs out of the saved files.
  3. Or hand-curate from prior research / academic citations.

Files in this directory are committed (small text); the fetched raw documents
in finetune/data/raw/ are gitignored.
