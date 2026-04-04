import os
import httpx
import logging

logger = logging.getLogger(__name__)
TURNSTILE_SECRET = os.getenv("CLOUDFLARE_TURNSTILE_SECRET", "")
TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str, remote_ip: str = "") -> bool:
    if not TURNSTILE_SECRET:
        return True
    if not token:
        return False
    try:
        payload = {"secret": TURNSTILE_SECRET, "response": token}
        if remote_ip:
            payload["remoteip"] = remote_ip
        async with httpx.AsyncClient() as client:
            r = await client.post(TURNSTILE_URL, data=payload, timeout=5)
            data = r.json()
            if not data.get("success"):
                logger.warning("Turnstile rejected: %s", data.get("error-codes"))
            return data.get("success", False)
    except Exception as e:
        logger.error("Turnstile verification error: %s", e)
        return False
