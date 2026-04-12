import logging
from fastapi import APIRouter, HTTPException, Request
from nanoid import generate
import time

from app.models import Session, SessionRequest, SessionResponse
from app.services.redis import get_knowledge_base, save_session, get_session
from app.services import analytics

router = APIRouter(tags=["session"])
logger = logging.getLogger(__name__)


@router.post("/session", response_model=SessionResponse)
async def create_session(body: SessionRequest, request: Request):
    kb = await get_knowledge_base(body.knowledge_base_id)
    if not kb:
        logger.warning("create_session: KB not found, kb_id=%s", body.knowledge_base_id)
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if kb.status != "complete":
        logger.warning(
            "create_session: KB not ready, kb_id=%s, status=%s",
            body.knowledge_base_id,
            kb.status,
        )
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
    logger.info(
        "create_session: created session_id=%s, kb_id=%s",
        session_id,
        body.knowledge_base_id,
    )

    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    source_domain = origin.replace("https://", "").replace("http://", "").split("/")[0]
    analytics.track(
        event_type="session_start",
        kb_id=body.knowledge_base_id,
        session_id=session_id,
        properties={"source_domain": source_domain},
    )

    pills = kb.suggested_pills if kb.suggested_pills else []
    name = kb.company_profile.name if kb.company_profile else ""
    return SessionResponse(session_id=session_id, pills=pills, language=kb.language, name=name)


@router.get("/session/{session_id}")
async def get_session_state(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
