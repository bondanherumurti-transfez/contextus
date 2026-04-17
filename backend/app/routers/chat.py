from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import json
import re
import time

from app.models import ChatRequest, Message
from app.services.redis import (
    get_session,
    save_session,
    get_knowledge_base,
    redis,
    extend_session_ttl,
)
from app.services.llm import stream_chat_response, build_waitlist_system_prompt
from app.services.telemetry import tracer
from app.services import analytics
from app.services.database import archive_session

router = APIRouter(tags=["chat"])

EMAIL_REGEX = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
PHONE_REGEX = re.compile(r"(\+62|08)\d{8,12}")
WA_REGEX = re.compile(r"wa\.me/\d+|whatsapp\.com")


def detect_contact(text: str) -> dict | None:
    email = EMAIL_REGEX.search(text)
    phone = PHONE_REGEX.search(text)
    wa = WA_REGEX.search(text)

    if email or phone or wa:
        return {
            "email": email.group(0) if email else None,
            "phone": phone.group(0) if phone else None,
            "whatsapp": wa.group(0) if wa else None,
        }
    return None


@router.post("/chat/{session_id}")
async def send_chat_message(session_id: str, body: ChatRequest, request: Request):
    start_time = time.time()
    span = tracer.start_span("chat.request")
    span.set_attribute("session_id", session_id)

    session = await get_session(session_id)
    if not session:
        span.end()
        raise HTTPException(status_code=404, detail="Session not found")

    kb = await get_knowledge_base(session.kb_id)
    if not kb:
        span.end()
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if not kb.company_profile:
        span.end()
        raise HTTPException(
            status_code=400, detail="Knowledge base has no company profile"
        )

    if len(session.messages) >= 60:
        span.end()
        raise HTTPException(
            status_code=429, detail="Session message limit reached (30 turns)"
        )

    span.set_attribute("kb_id", session.kb_id)
    span.set_attribute("message_count", len(session.messages))

    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    source_domain = origin.replace("https://", "").replace("http://", "").split("/")[0]
    analytics.track(
        event_type="message_sent",
        kb_id=session.kb_id,
        session_id=session_id,
        properties={
            "source_domain": source_domain,
            "message_count": len(session.messages) // 2 + 1,
        },
    )

    contact = detect_contact(body.message)
    newly_captured = False
    if contact and not session.contact_captured:
        session.contact_captured = True
        session.contact_value = json.dumps(contact)
        newly_captured = True

    waitlist_prompt = None
    raw_prefill = await redis.get(f"waitlist:{session_id}")
    if raw_prefill:
        prefill = json.loads(raw_prefill)
        waitlist_prompt = build_waitlist_system_prompt(
            prefill.get("name", ""), prefill.get("website", "")
        )

    messages = [{"role": msg.role, "content": msg.text} for msg in session.messages]

    async def generate():
        full_text = ""
        try:
            async for chunk in stream_chat_response(
                messages,
                kb.company_profile,
                kb.chunks,
                body.message,
                system_prompt_override=waitlist_prompt,
                kb_id=session.kb_id,
            ):
                full_text += chunk
                yield f"data: {json.dumps({'token': chunk})}\n\n"

            yield f"data: {json.dumps({'done': True, 'full_text': full_text})}\n\n"

            session.messages.append(
                Message(role="user", text=body.message, timestamp=int(time.time()))
            )
            session.messages.append(
                Message(role="assistant", text=full_text, timestamp=int(time.time()))
            )
            await save_session(session_id, session)
            await archive_session(session)

            if newly_captured:
                await extend_session_ttl(session_id, ttl=86400)
                analytics.track(
                    event_type="contact_captured",
                    kb_id=session.kb_id,
                    session_id=session_id,
                    properties={"source_domain": source_domain},
                )

            span.set_attribute("response_length", len(full_text))
            span.set_attribute(
                "total_duration_ms", int((time.time() - start_time) * 1000)
            )

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            span.end()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
