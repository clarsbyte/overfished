#!/usr/bin/env python3
"""Generate TypeScript interfaces from backend/tools/schemas.py.

Walks Pydantic v2 models and emits hand-formatted TS to
``frontend/src/types/schemas.ts``. We hand-roll instead of using
``pydantic-to-typescript`` because that package mishandles ``Literal`` unions
under Pydantic v2.

Run from repo root::

    python3 scripts/generate_ts_types.py
"""

from __future__ import annotations

import inspect
import sys
import types
import typing
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from pydantic import BaseModel  # noqa: E402

import tools.schemas as schemas_mod  # noqa: E402

OUT = REPO / "frontend" / "src" / "types" / "schemas.ts"


def py_type_to_ts(tp, model_names: set[str]) -> str:
    """Convert a Python typing annotation to a TypeScript type string."""
    # None / NoneType
    if tp is type(None):  # noqa: E721
        return "null"

    origin = typing.get_origin(tp)
    args = typing.get_args(tp)

    # Optional[X] / X | None — represented as Union with NoneType
    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        nullable = len(non_none) != len(args)
        rendered = " | ".join(py_type_to_ts(a, model_names) for a in non_none)
        return f"{rendered} | null" if nullable else rendered

    # Literal[...]
    if origin is typing.Literal:
        return " | ".join(repr(a) if not isinstance(a, str) else f'"{a}"' for a in args)

    # list[X]
    if origin in (list, typing.List):
        inner = py_type_to_ts(args[0], model_names) if args else "unknown"
        return f"{inner}[]"

    # dict[K, V]
    if origin in (dict, typing.Dict):
        if args:
            k = py_type_to_ts(args[0], model_names)
            v = py_type_to_ts(args[1], model_names)
            return f"Record<{k}, {v}>"
        return "Record<string, unknown>"

    # tuple[...]
    if origin in (tuple, typing.Tuple):
        return "[" + ", ".join(py_type_to_ts(a, model_names) for a in args) + "]"

    # Concrete classes
    if isinstance(tp, type):
        if tp is str:
            return "string"
        if tp is bool:
            return "boolean"
        if tp in (int, float):
            return "number"
        if tp is datetime:
            return "string"
        if tp is dict:
            return "Record<string, unknown>"
        if tp.__name__ in model_names:
            return tp.__name__

    return "unknown"


def emit_interface(model: type[BaseModel], model_names: set[str]) -> str:
    lines = [f"export interface {model.__name__} {{"]
    for fname, finfo in model.model_fields.items():
        ts = py_type_to_ts(finfo.annotation, model_names)
        # Optional fields (Pydantic v2: not is_required()) get `?`
        optional = "?" if not finfo.is_required() else ""
        lines.append(f"  {fname}{optional}: {ts};")
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    models: list[type[BaseModel]] = [
        cls
        for _, cls in inspect.getmembers(schemas_mod, inspect.isclass)
        if issubclass(cls, BaseModel) and cls.__module__ == schemas_mod.__name__ and cls.__name__ != "_Strict"
    ]

    # Sort so dependencies come first (LatLon before things that use it, etc.).
    # Simple heuristic: name length asc, then alpha — works because LatLon is short.
    # For correctness, do a topo sort over field-type references.
    model_names = {m.__name__ for m in models}

    # Topological sort
    deps: dict[str, set[str]] = {m.__name__: set() for m in models}
    for m in models:
        for f in m.model_fields.values():
            for arg in _walk_types(f.annotation):
                if isinstance(arg, type) and arg.__name__ in model_names and arg.__name__ != m.__name__:
                    deps[m.__name__].add(arg.__name__)

    ordered: list[str] = []
    while deps:
        ready = sorted(n for n, d in deps.items() if not d)
        if not ready:
            ordered.extend(sorted(deps))  # cycle (shouldn't happen) — emit anyway
            break
        for n in ready:
            ordered.append(n)
            del deps[n]
        for d in deps.values():
            d.difference_update(ready)

    by_name = {m.__name__: m for m in models}

    banner = (
        "// AUTO-GENERATED — DO NOT EDIT.\n"
        "// Regenerate via: python3 scripts/generate_ts_types.py\n"
        "// Source: backend/tools/schemas.py\n\n"
    )
    body = "\n\n".join(emit_interface(by_name[n], model_names) for n in ordered) + "\n"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(banner + body)
    print(f"wrote {OUT.relative_to(REPO)}  ({len(ordered)} interfaces)")


def _walk_types(tp):
    """Yield every concrete class referenced inside a typing annotation."""
    yield tp
    for a in typing.get_args(tp) or ():
        yield from _walk_types(a)


if __name__ == "__main__":
    main()
