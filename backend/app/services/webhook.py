import asyncio
import logging
import httpx

from app.models import LeadBrief

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [1, 2, 4]  # seconds between attempts


async def fire_webhook(url: str, brief: LeadBrief) -> None:
    payload = brief.model_dump()
    async with httpx.AsyncClient(timeout=10) as client:
        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info(
                    "[webhook] delivered session_id=%s to %s (attempt %d, status %d)",
                    brief.session_id, url, attempt, resp.status_code,
                )
                return
            except Exception as e:
                logger.warning(
                    "[webhook] attempt %d failed for session_id=%s: %s",
                    attempt, brief.session_id, e,
                )
                if attempt < len(_RETRY_DELAYS):
                    await asyncio.sleep(delay)

    logger.error(
        "[webhook] all attempts exhausted for session_id=%s url=%s",
        brief.session_id, url,
    )
