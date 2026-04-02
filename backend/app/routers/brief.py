from fastapi import APIRouter, HTTPException

from app.models import LeadBrief
from app.services.redis import get_session, get_knowledge_base
from app.services.llm import generate_lead_brief

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

    return brief
