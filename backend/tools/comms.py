"""Voice broadcasts — ElevenLabs in real mode, static URL in fixture mode."""

from __future__ import annotations

import os

from tools.schemas import RegionContext, RiskAssessment, Vessel

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"


def generate_cease_and_desist_audio(
    vessel: Vessel,
    risk: RiskAssessment,
    region: RegionContext,
) -> str:
    """Generate the broadcast script and synthesize via ElevenLabs.

    Returns the URL to the rendered MP3.
    """
    if _USE_FIXTURES:
        # TODO(chan): wire ElevenLabs once the voice ID is locked.
        return f"/static/audio/cease_{vessel.mmsi}.mp3"
    raise NotImplementedError("set USE_FIXTURES=1")


def build_cease_and_desist_script(
    vessel: Vessel,
    region: RegionContext,
) -> str:
    """Render the radio-broadcast script (template fill, no LLM in fixture mode)."""
    return (
        f"Attention vessel MMSI {vessel.mmsi}, this is the {region.name} Authority. "
        f"You are inside a protected marine area. Cease all fishing operations and "
        f"exit the protected area immediately. Failure to comply will result in "
        f"interdiction and prosecution under Port State Measures Agreement Article 9."
    )
