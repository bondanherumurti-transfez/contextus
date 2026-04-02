from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json
import re
import time

from app.models import ChatRequest, Message
from app.services.redis import get_session, save_session, get_knowledge_base, redis, extend_session_ttl
from app.services.llm import stream_chat_response, build_waitlist_system_prompt

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
async def send_chat_message(session_id: str, body: ChatRequest):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    kb = await get_knowledge_base(session.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if not kb.company_profile:
        raise HTTPException(
            status_code=400, detail="Knowledge base has no company profile"
        )

    if len(session.messages) >= 60:
        raise HTTPException(
            status_code=429, detail="Session message limit reached (30 turns)"
        )

    contact = detect_contact(body.message)
    newly_captured = False
    if contact and not session.contact_captured:
        session.contact_captured = True
        session.contact_value = json.dumps(contact)
        newly_captured = True

    # Detect waitlist session — use waitlist system prompt if prefill exists
    waitlist_prompt = None
    raw_prefill = redis.get(f"waitlist:{session_id}")
    if raw_prefill:
        prefill = json.loads(raw_prefill)
        waitlist_prompt = build_waitlist_system_prompt(
            prefill.get("name", ""), prefill.get("website", "")
        )

    messages = [{"role": msg.role, "content": msg.text} for msg in session.messages]

    async def generate():
        full_text = ""
        try:
            for token in stream_chat_response(
                messages, kb.company_profile, kb.chunks, body.message,
                system_prompt_override=waitlist_prompt,
            ):
                full_text += token
                yield f"data: {json.dumps({'token': token})}\n\n"

            yield f"data: {json.dumps({'done': True, 'full_text': full_text})}\n\n"

            session.messages.append(
                Message(role="user", text=body.message, timestamp=int(time.time()))
            )
            session.messages.append(
                Message(role="assistant", text=full_text, timestamp=int(time.time()))
            )
            await save_session(session_id, session)

            # Extend TTL to 24hr when contact is first captured so cron can process it
            if newly_captured:
                await extend_session_ttl(session_id, ttl=86400)

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
