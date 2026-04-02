import json
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from nanoid import generate

from app.services.redis import redis, save_session, get_session
from app.models import Session
from app.services.notion import post_waitlist_to_notion
from app.services.llm import extract_waitlist_context

router = APIRouter(tags=["waitlist"])


class WaitlistStartRequest(BaseModel):
    name: str
    email: str
    website: str
    phone: str | None = None


class WaitlistSubmitRequest(BaseModel):
    session_id: str


@router.post("/waitlist/start")
async def waitlist_start(body: WaitlistStartRequest):
    session_id = generate(size=10)

    session = Session(
        session_id=session_id,
        kb_id="demo",
        messages=[],
        contact_captured=True,
        contact_value=body.email,
        created_at=int(time.time()),
    )

    redis.set(
        f"waitlist:{session_id}",
        json.dumps({
            "name": body.name,
            "email": body.email,
            "website": body.website,
            "phone": body.phone or "",
        }),
        ex=3600,
    )

    await save_session(session_id, session)
    return {"session_id": session_id}


@router.post("/waitlist/submit")
async def waitlist_submit(body: WaitlistSubmitRequest):
    raw = redis.get(f"waitlist:{body.session_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Waitlist session not found")

    prefill = json.loads(raw)
    session = await get_session(body.session_id)

    context = {"business_type": "", "goal": "", "agent_behavior": "", "timeline": ""}
    if session and session.messages:
        transcript = "\n".join(f"{m.role}: {m.text}" for m in session.messages)
        context = extract_waitlist_context(transcript)

    await post_waitlist_to_notion({
        **prefill,
        "business_type": context.get("business_type", ""),
        "goal": context.get("goal", ""),
        "agent_behavior": context.get("agent_behavior", ""),
        "timeline": context.get("timeline", ""),
        "session_id": body.session_id,
    })

    return {"status": "ok"}
