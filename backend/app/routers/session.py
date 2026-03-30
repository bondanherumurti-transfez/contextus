from fastapi import APIRouter, HTTPException
from nanoid import generate
import time

from app.models import Session, SessionRequest, SessionResponse
from app.services.redis import get_knowledge_base, save_session, get_session

router = APIRouter(tags=["session"])


@router.post("/session", response_model=SessionResponse)
async def create_session(body: SessionRequest):
    kb = await get_knowledge_base(body.knowledge_base_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if kb.status != "complete":
        raise HTTPException(status_code=400, detail="Knowledge base not ready")

    session_id = generate(size=10)

    session = Session(
        session_id=session_id,
        kb_id=body.knowledge_base_id,
        messages=[],
        contact_captured=False,
        created_at=int(time.time()),
    )

    await save_session(session_id, session)

    return SessionResponse(session_id=session_id)


@router.get("/session/{session_id}")
async def get_session_state(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
