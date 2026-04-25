"""CLI / argparse behavior for image_enrichment.build_all."""

from __future__ import annotations

import sys

import pytest

from overfished_ml.image_enrichment.build_all import build_parser, main


def test_build_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.skip_resolve is False
    assert args.skip_download is False
    assert args.refresh is False


def test_main_rejects_conflicting_commons_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_all", "--use-commons-fallback", "--no-commons-fallback"],
    )
    with pytest.raises(SystemExit):
        main()
