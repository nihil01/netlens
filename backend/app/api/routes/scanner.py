from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.ip_intelligence.schemas import ScannerProfilesResponse
from app.scanner.store import ScannerProfileStore

router = APIRouter()
profile_store = ScannerProfileStore()


@router.get("/scanner/profiles", response_model=ScannerProfilesResponse)
async def get_scanner_profiles(
    _: Annotated[dict, Depends(get_current_user)],
) -> ScannerProfilesResponse:
    return ScannerProfilesResponse.model_validate(await profile_store.get_latest())
