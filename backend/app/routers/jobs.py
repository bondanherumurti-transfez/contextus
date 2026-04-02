import json
import logging
import os

from fastapi import APIRouter, Header, HTTPException

from app.services.redis import redis, scan_all_sessions, save_session
from app.services.llm import generate_lead_brief
from app.services.notion import post_lead_brief_to_notion
from app.services.database import get_customer_config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["jobs"])

CRON_SECRET = os.getenv("CRON_SECRET", "")


def _is_meaningful(session, is_waitlist: bool) -> bool:
    """Decide if a session is worth generating a brief for."""
    if is_waitlist:
        return True  # always process — has name/email/website at minimum
    if len(session.messages) < 3:
        return False
    return session.contact_captured or len(session.messages) >= 5


@router.post("/jobs/process-sessions")
async def process_sessions(x_cron_secret: str | None = Header(default=None)):
    if CRON_SECRET and x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    sessions = await scan_all_sessions()
    results = {"processed": 0, "skipped_tagged": 0, "skipped_thin": 0, "failed": 0}

    for session in sessions:
        if session.brief_sent:
            results["skipped_tagged"] += 1
            continue

        # Check if this is a waitlist session
        raw_prefill = redis.get(f"waitlist:{session.session_id}")
        is_waitlist = raw_prefill is not None
        prefill = json.loads(raw_prefill) if raw_prefill else {}

        if not _is_meaningful(session, is_waitlist):
            results["skipped_thin"] += 1
            continue

        try:
            brief = generate_lead_brief(session)

            # Look up per-customer Notion DB
            customer_config = await get_customer_config(session.kb_id) if session.kb_id else None
            customer_notion_db = customer_config.get("notion_db_id") if customer_config else None

            notion_data = {
                **brief.model_dump(),
                "kb_id": session.kb_id,
                "is_waitlist": is_waitlist,
                # Enrich with prefill data for waitlist sessions
                "email": prefill.get("email") or (brief.contact and brief.contact.get("email")),
                "phone": prefill.get("phone") or (brief.contact and brief.contact.get("phone")),
                "website": prefill.get("website"),
            }

            success = await post_lead_brief_to_notion(notion_data, notion_db_id=customer_notion_db)

            if success is not False:
                session.brief_sent = True
                await save_session(session.session_id, session)
                results["processed"] += 1
            else:
                results["failed"] += 1

        except Exception as e:
            logger.error("Failed to process session %s: %s", session.session_id, e)
            results["failed"] += 1

    logger.info("process-sessions results: %s", results)
    return results
