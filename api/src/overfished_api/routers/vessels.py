from fastapi import APIRouter

router = APIRouter(prefix="/vessels", tags=["vessels"])


@router.get("/{vessel_id}")
async def get_vessel(vessel_id: str) -> dict[str, str]:
    return {"vessel_id": vessel_id, "detail": "not_implemented"}
