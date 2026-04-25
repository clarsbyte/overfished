from fastapi import APIRouter

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("/{region_id}")
async def get_region(region_id: str) -> dict[str, str]:
    return {"region_id": region_id, "detail": "not_implemented"}
