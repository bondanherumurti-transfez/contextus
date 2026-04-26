from fastapi import APIRouter, Depends

from app.routers.auth import get_current_user
from app.services.portal_db import UserRow, db_get_user_sites

router = APIRouter(prefix="/api/portal", tags=["portal"])


@router.get("/sites")
async def list_sites(user: UserRow = Depends(get_current_user)):
    sites = await db_get_user_sites(user["user_id"])
    return {"sites": sites}
