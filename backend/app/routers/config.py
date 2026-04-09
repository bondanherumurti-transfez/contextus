import os
import logging
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.services.database import get_customer_config, save_customer_config

router = APIRouter(tags=["config"])
logger = logging.getLogger(__name__)

ADMIN_TOKEN = os.getenv("ADMIN_SECRET", "")


def _check_auth(authorization: str | None) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")
    if authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


class WebhookUpdate(BaseModel):
    webhook_url: str | None = None


@router.put("/config/{kb_id}/webhook")
async def set_webhook(
    kb_id: str,
    body: WebhookUpdate,
    authorization: str | None = Header(default=None),
):
    _check_auth(authorization)

    config = await get_customer_config(kb_id) or {}
    config["kb_id"] = kb_id
    config["webhook_url"] = body.webhook_url

    await save_customer_config(config)
    logger.info("[config] webhook_url updated for kb_id=%s", kb_id)
    return {"kb_id": kb_id, "webhook_url": body.webhook_url}


@router.get("/config/{kb_id}")
async def get_config(
    kb_id: str,
    authorization: str | None = Header(default=None),
):
    _check_auth(authorization)

    config = await get_customer_config(kb_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return config
