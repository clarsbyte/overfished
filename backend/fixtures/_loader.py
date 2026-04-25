"""Fixture loader — reads JSON from this directory and validates against a schema.

Used by every tool in fixture mode and by the test suite. Always validates on
load so a malformed fixture surfaces immediately, not at the call site.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

FIXTURES_DIR = Path(__file__).resolve().parent

T = TypeVar("T", bound=BaseModel)


def load_raw(name: str) -> dict | list:
    """Read a fixture JSON file by name (without extension) and return the raw value."""
    path = FIXTURES_DIR / f"{name}.json"
    with path.open() as f:
        return json.load(f)


def load_model(name: str, model: type[T]) -> T:
    """Read a fixture JSON file and validate it as ``model``."""
    return model.model_validate(load_raw(name))


def load_models(name: str, model: type[T]) -> list[T]:
    """Read a fixture JSON file expected to be a list and validate each element."""
    raw = load_raw(name)
    if not isinstance(raw, list):
        raise ValueError(f"Fixture {name!r} is not a list (got {type(raw).__name__}).")
    return [model.model_validate(item) for item in raw]
