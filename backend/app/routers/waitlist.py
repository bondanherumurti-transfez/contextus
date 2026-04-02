import json
import os
import time
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from nanoid import generate

from app.services.redis import redis, save_session, get_session, extend_session_ttl
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

    await redis.set(
        f"waitlist:{session_id}",
        json.dumps(
            {
                "name": body.name,
                "email": body.email,
                "website": body.website,
                "phone": body.phone or "",
            }
        ),
        ex=3600,
    )

    await save_session(session_id, session)
    await extend_session_ttl(session_id, ttl=86400)
    return {"session_id": session_id}


@router.post("/waitlist/submit")
async def waitlist_submit(body: WaitlistSubmitRequest):
    raw = await redis.get(f"waitlist:{body.session_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Waitlist session not found")

    prefill = json.loads(raw)
    session = await get_session(body.session_id)

    context = {"business_type": "", "goal": "", "agent_behavior": "", "timeline": ""}
    if session and session.messages:
        transcript = "\n".join(f"{m.role}: {m.text}" for m in session.messages)
        context = await extract_waitlist_context(transcript)

    await post_waitlist_to_notion(
        {
            **prefill,
            "business_type": context.get("business_type", ""),
            "goal": context.get("goal", ""),
            "agent_behavior": context.get("agent_behavior", ""),
            "timeline": context.get("timeline", ""),
            "session_id": body.session_id,
        }
    )

    return {"status": "ok"}


@router.get("/waitlist/test-notion")
async def test_notion():
    token = os.getenv("NOTION_TOKEN", "")
    database_id = os.getenv("NOTION_DB_WAITLIST", "")

    if not token:
        return {"error": "NOTION_TOKEN not set"}
    if not database_id:
        return {"error": "NOTION_DB_WAITLIST not set"}

    def txt(val):
        return [{"text": {"content": str(val or "—")}}]

    page = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {"title": txt("Test Entry")},
            "Email": {"email": "test@contextus.ai"},
            "Website": {"url": "https://contextus.ai"},
            "Phone": {"phone_number": "+628123456789"},
            "Business Type": {"rich_text": txt("SaaS")},
            "Goal": {"rich_text": txt("Lead generation")},
            "Agent Behavior": {"rich_text": txt("Friendly and concise")},
            "Timeline": {"rich_text": txt("ASAP")},
            "Session": {"rich_text": txt("test-session-debug")},
        },
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.notion.com/v1/pages",
            json=page,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

    return {
        "notion_status": res.status_code,
        "notion_response": res.json(),
        "token_prefix": token[:12] + "...",
        "database_id": database_id,
    }
