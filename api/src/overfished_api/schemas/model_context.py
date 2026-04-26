"""Typed static runtime context the FE attaches to POST /agent/run.

Maps the LangChain "static runtime context" concept onto our LangChain
Classic stack: the FE builds this dict from the latest sequence report, the
agent backend forwards it to ``pipeline_agent.evaluate_incident`` /
``regional_agent.evaluate_point``, and those prepend a formatted block to
the supervisor's input string. See:
https://docs.langchain.com/oss/python/concepts/context
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ModelRisk = Literal["safe", "uncertain", "spoof_suspect"]


class PerMmsiSummary(BaseModel):
    mmsi: str
    n_windows: int
    top1_match_rate: float
    mean_confidence: float
    alias_mmsi: str | None = None
    alias_share: float = 0.0
    model_risk: ModelRisk
    narration: str


class ModelContext(BaseModel):
    """Static runtime context for one agent run.

    `selected` is the vessel the operator has highlighted in the UI; `nearby`
    is a small list of other flagged vessels the agent might encounter while
    investigating; `report_narration` is the model-level one-liner.
    """

    selected: PerMmsiSummary | None = None
    nearby: list[PerMmsiSummary] = Field(default_factory=list)
    report_narration: str | None = None
    generated_at: str | None = None
    source: Literal["demo", "canonical"] | None = None


def format_model_context_block(ctx: ModelContext | dict | None) -> str:
    """Render the ModelContext as a prompt-ready text block.

    Empty/None context -> empty string (caller should skip prepend).
    """
    if ctx is None:
        return ""
    if isinstance(ctx, dict):
        try:
            ctx = ModelContext.model_validate(ctx)
        except Exception:
            return ""
    if ctx.selected is None and not ctx.nearby and not ctx.report_narration:
        return ""

    lines = [
        "MODEL CONTEXT (RNN+BiLSTM, soft-prob ensemble; treat as triage signal, not ground truth):",
    ]
    sel = ctx.selected
    if sel is not None:
        risk_tag = sel.model_risk.upper()
        alias_bit = (
            f", alias candidate {sel.alias_mmsi} in {sel.alias_share:.0%} of windows"
            if sel.alias_mmsi
            else ""
        )
        lines.append(
            f"- Selected MMSI {sel.mmsi} -> {risk_tag} (mean P {sel.mean_confidence:.0%}{alias_bit})."
        )
        lines.append(f"  {sel.narration}")
    if ctx.nearby:
        nearby_bits = []
        for n in ctx.nearby[:5]:
            nearby_bits.append(
                f"{n.mmsi} ({n.model_risk.upper()}, P {n.mean_confidence:.0%})"
            )
        lines.append(f"- Nearby flagged: {'; '.join(nearby_bits)}.")
    if ctx.report_narration:
        lines.append(f"- Report summary: {ctx.report_narration}")
    if ctx.source or ctx.generated_at:
        lines.append(
            f"- Source: {ctx.source or 'unknown'}; generated_at: {ctx.generated_at or 'n/a'}."
        )
    return "\n".join(lines)
