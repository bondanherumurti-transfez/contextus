import asyncio
from fastapi import APIRouter, HTTPException

from app.models import LeadBrief
from app.services.redis import get_session, get_knowledge_base
from app.services.llm import generate_lead_brief
from app.services.database import get_customer_config, db_mark_brief_sent
from app.services.webhook import fire_webhook
from app.services import analytics

router = APIRouter(tags=["brief"])


@router.post("/brief/{session_id}", response_model=LeadBrief)
async def generate_brief(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if len(session.messages) < 2:
        raise HTTPException(
            status_code=400, detail="Need at least 2 messages to generate a brief"
        )

    kb = await get_knowledge_base(session.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    brief = await generate_lead_brief(session)

    config = await get_customer_config(session.kb_id)
    if config and config.get("webhook_url"):
        asyncio.create_task(fire_webhook(config["webhook_url"], brief))

    asyncio.create_task(db_mark_brief_sent(session_id))

    analytics.track(
        event_type="brief_generated",
        kb_id=session.kb_id,
        session_id=session_id,
        properties={"message_count": len(session.messages) // 2},
    )

    return brief
