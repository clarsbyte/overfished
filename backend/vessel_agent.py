"""LangChain agent that checks AISStream.io for vessels near a coordinate.

Run as a CLI:
    python vessel_agent.py <x_longitude> <y_latitude> [radius_miles]

Or import and call `run_agent(x, y, radius)`.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from services.llm import build_chat_llm
from vessel_lookup import vessels_within_radius

load_dotenv()


@tool
def check_vessels_near(
    latitude: float,
    longitude: float,
    radius_miles: float = 100.0,
    listen_seconds: float = 30.0,
) -> str:
    """Listen to AISStream.io for vessels within `radius_miles` of (latitude, longitude).

    AIS is a broadcast feed, so this call blocks for `listen_seconds` while
    collecting position reports in the surrounding bounding box, then filters
    to the true radius. Moving vessels broadcast every few seconds; stationary
    vessels every ~3 minutes — increase `listen_seconds` to catch anchored ships.

    Args:
        latitude: latitude in decimal degrees (positive north, negative south).
        longitude: longitude in decimal degrees (positive east, negative west).
        radius_miles: search radius in statute miles. Defaults to 100.
        listen_seconds: how long to listen to the AIS stream. Defaults to 30.

    Returns:
        Human-readable summary of vessels found, ordered by distance.
    """
    try:
        vessels = vessels_within_radius(latitude, longitude, radius_miles, listen_seconds)
    except Exception as exc:  # network / parsing failures bubble up to the LLM as text
        return (
            f"Failed to query AISStream.io for ({latitude}, {longitude}) "
            f"within {radius_miles} mi: {exc!s}"
        )

    if not vessels:
        return (
            f"No vessels detected via AISStream.io within {radius_miles:.0f} miles "
            f"of ({latitude}, {longitude}) during a {listen_seconds:.0f}s listen window."
        )

    header = (
        f"Found {len(vessels)} vessel(s) within {radius_miles:.0f} miles of "
        f"({latitude}, {longitude}):"
    )
    body = "\n".join(v.as_line() for v in vessels[:25])
    if len(vessels) > 25:
        body += f"\n…and {len(vessels) - 25} more."
    return f"{header}\n{body}"


SYSTEM_PROMPT = (
    "You are a maritime lookup assistant backed by live AIS data from "
    "AISStream.io. When the user gives coordinates (x = longitude, y = latitude "
    "in the GIS convention), call the check_vessels_near tool exactly once with "
    "those coordinates and the requested radius (default 100 miles). The tool "
    "blocks for ~30 seconds while it listens to the AIS stream — this is "
    "expected, not a hang. Then answer plainly: state whether any vessels were "
    "found, and if so list the closest few with their names, types, and "
    "distance from the query point."
)


def build_agent_executor(model: str | None = None) -> AgentExecutor:
    llm = build_chat_llm("light", model=model)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    tools = [check_vessels_near]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


def run_agent(x_longitude: float, y_latitude: float, radius_miles: float = 100.0) -> str:
    executor = build_agent_executor()
    question = (
        f"Are there any vessels within {radius_miles} miles of "
        f"x={x_longitude} (longitude), y={y_latitude} (latitude)? "
        "Use the tool to check the AIS stream and report what you find."
    )
    result = executor.invoke({"input": question})
    return result["output"] if isinstance(result, dict) else str(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check AISStream.io for vessels near (x, y).")
    parser.add_argument("x", type=float, help="x coordinate (longitude, decimal degrees)")
    parser.add_argument("y", type=float, help="y coordinate (latitude, decimal degrees)")
    parser.add_argument("radius", type=float, nargs="?", default=100.0, help="radius in miles")
    args = parser.parse_args()

    print(run_agent(args.x, args.y, args.radius))


if __name__ == "__main__":
    main()
