from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FishingDataSource(Protocol):
    """Future: vessel tracks, effort grids, events from upstream APIs."""

    async def fetch_region_summary(self, region_id: str) -> dict[str, Any]:
        ...

    async def fetch_vessel_profile(self, vessel_id: str) -> dict[str, Any]:
        ...


@runtime_checkable
class RegulationSource(Protocol):
    """Future: regional rules and citations."""

    async def fetch_regulations(self, region_id: str) -> dict[str, Any]:
        ...
