import base64
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import (
    CompanyProfile,
    CompanyProfileResponse,
    EnrichedChunk,
    KBResponse,
    KnowledgeBase,
    PortalCustomInstructionsRequest,
    PortalEnrichRequest,
    PortalGreetingRequest,
    PortalPillsRequest,
    SessionDetailResponse,
    SessionListResponse,
)
from app.routers.auth import get_current_user, get_current_user_for_kb
from app.routers.crawl import enrich_kb, update_custom_instructions_kb, update_pills_kb
from app.services.portal_db import (
    UserRow,
    db_get_kb,
    db_get_session,
    db_get_user_sites,
    db_list_sessions,
    db_update_greeting,
    db_user_has_kb_access,
)
from app.services.redis import check_rate_limit, get_knowledge_base

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portal", tags=["portal"])

_MAX_LIMIT = 200


def _extract_preview(messages: list[dict]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("text") or msg.get("content") or ""
            return text[:80]
    if messages:
        msg = messages[0]
        text = msg.get("text") or msg.get("content") or ""
        return text[:80]
    return ""


def _encode_cursor(updated_at: int) -> str:
    return base64.b64encode(str(updated_at).encode()).decode()


def _decode_cursor(cursor: str) -> int | None:
    try:
        return int(base64.b64decode(cursor).decode())
    except Exception:
        return None


def _derive_enriched_chunks(chunks: list) -> list[EnrichedChunk]:
    result = []
    for chunk in (chunks or []):
        source = chunk.source if hasattr(chunk, "source") else chunk.get("source", "")
        if source.startswith("interview:"):
            question = source[len("interview:"):]
            answer = chunk.text if hasattr(chunk, "text") else chunk.get("text", "")
            word_count = chunk.word_count if hasattr(chunk, "word_count") else len(answer.split())
            chunk_id = chunk.id if hasattr(chunk, "id") else chunk.get("id", "")
            result.append(EnrichedChunk(
                id=chunk_id,
                question=question,
                answer=answer,
                word_count=word_count,
            ))
    return result


@router.get("/kb", response_model=KBResponse)
async def get_kb(
    kb_id: str = Query(...),
    user: UserRow = Depends(get_current_user),
):
    await get_current_user_for_kb(kb_id, user)

    try:
        row = await db_get_kb(kb_id)
    except Exception as e:
        logger.error("get_kb: DB error: %s", e)
        raise HTTPException(503, {"error": "service temporarily unavailable"})

    if not row:
        raise HTTPException(404, {"error": "kb not found"})

    kb = KnowledgeBase.model_validate_json(row["kb_data"])

    company_profile_resp = None
    if kb.company_profile:
        cp = kb.company_profile
        company_profile_resp = CompanyProfileResponse(
            name=cp.name,
            industry=cp.industry,
            services=", ".join(cp.services) if cp.services else None,
            out_of_scope=", ".join(cp.out_of_scope) if cp.out_of_scope else None,
            summary=cp.summary,
            last_crawled_at=row["updated_at"],
            pages_indexed=kb.pages_found or None,
        )

    return KBResponse(
        kb_id=kb_id,
        company_profile=company_profile_resp,
        enriched_chunks=_derive_enriched_chunks(kb.chunks),
        pills=kb.suggested_pills or [],
        greeting=row["greeting"],
        custom_instructions=kb.company_profile.custom_instructions if kb.company_profile else None,
    )


@router.get("/sites")
async def list_sites(user: UserRow = Depends(get_current_user)):
    sites = await db_get_user_sites(user["user_id"])
    return {"sites": sites}


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    kb_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    cursor: str | None = Query(default=None),
    user: UserRow = Depends(get_current_user),
):
    await get_current_user_for_kb(kb_id, user)

    cursor_updated_at = _decode_cursor(cursor) if cursor else None
    rows = await db_list_sessions(kb_id, limit, cursor_updated_at)

    sessions = []
    for r in rows:
        messages = r.get("messages") or []
        if isinstance(messages, str):
            messages = json.loads(messages)
        sessions.append({
            "session_id": r["session_id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "message_count": r["message_count"] or 0,
            "contact_captured": bool(r["contact_captured"]),
            "contact_value": r.get("contact_value"),
            "preview": _extract_preview(messages),
            "qualification": r.get("qualification"),
            "quality_score": r.get("quality_score"),
            "brief_sent": bool(r.get("brief_sent")),
        })

    next_cursor = None
    if len(rows) == limit:
        next_cursor = _encode_cursor(rows[-1]["updated_at"])

    return {"sessions": sessions, "next_cursor": next_cursor}


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    user: UserRow = Depends(get_current_user),
):
    try:
        row = await db_get_session(session_id)
    except Exception as e:
        logger.error("get_session_detail: DB error: %s", e)
        raise HTTPException(503, {"error": "service temporarily unavailable"})

    if not row:
        raise HTTPException(404, {"error": "session not found"})

    try:
        has_access = await db_user_has_kb_access(user["user_id"], row["kb_id"])
    except Exception as e:
        logger.error("get_session_detail: access check DB error: %s", e)
        raise HTTPException(503, {"error": "service temporarily unavailable"})

    if not has_access:
        raise HTTPException(403, {"error": "forbidden"})

    messages = row.get("messages") or []
    if isinstance(messages, str):
        messages = json.loads(messages)

    brief_data = row.get("brief_data")
    if isinstance(brief_data, str):
        brief_data = json.loads(brief_data)

    return {
        "session": {
            "session_id": row["session_id"],
            "kb_id": row["kb_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"] or 0,
            "messages": messages,
            "contact_captured": bool(row["contact_captured"]),
            "contact_value": row.get("contact_value"),
            "brief_sent": bool(row.get("brief_sent")),
        },
        "brief": brief_data,
    }


_ENRICH_RATE_LIMIT = 10
_ENRICH_RATE_WINDOW = 600  # 10 minutes


@router.post("/kb/enrich", response_model=CompanyProfile)
async def portal_enrich_kb(
    body: PortalEnrichRequest,
    user: UserRow = Depends(get_current_user),
):
    if not body.question or len(body.question) > 200:
        raise HTTPException(422, {"error": "question must be 1–200 characters"})
    if not body.answer or len(body.answer) > 2000:
        raise HTTPException(422, {"error": "answer must be 1–2000 characters"})

    await get_current_user_for_kb(body.kb_id, user)

    kb = await get_knowledge_base(body.kb_id)
    if not kb:
        raise HTTPException(404, {"error": "kb not found"})
    if kb.status != "complete":
        raise HTTPException(400, {"error": "kb_not_ready"})

    if not await check_rate_limit(user["user_id"], "enrich", _ENRICH_RATE_LIMIT, _ENRICH_RATE_WINDOW):
        raise HTTPException(429, {"error": "rate_limit_exceeded", "retry_after": _ENRICH_RATE_WINDOW})

    return await enrich_kb(kb, body.kb_id, {body.question: body.answer}, permanent=True)


@router.patch("/kb/pills")
async def portal_update_pills(
    body: PortalPillsRequest,
    user: UserRow = Depends(get_current_user),
):
    if len(body.pills) != 3 or any(not p.strip() for p in body.pills):
        raise HTTPException(422, {"error": "pills must be exactly 3 non-empty strings"})

    await get_current_user_for_kb(body.kb_id, user)

    kb = await get_knowledge_base(body.kb_id)
    if not kb:
        raise HTTPException(404, {"error": "kb not found"})

    await update_pills_kb(kb, body.kb_id, body.pills, permanent=True)
    return {"ok": True}


@router.patch("/kb/greeting")
async def portal_update_greeting(
    body: PortalGreetingRequest,
    user: UserRow = Depends(get_current_user),
):
    await get_current_user_for_kb(body.kb_id, user)

    value = body.greeting.strip() if body.greeting else None
    value = value or None
    if value is not None and len(value) > 200:
        raise HTTPException(422, {"error": "greeting must be at most 200 characters"})

    kb = await get_knowledge_base(body.kb_id)
    if not kb:
        raise HTTPException(404, {"error": "kb not found"})

    try:
        await db_update_greeting(body.kb_id, value)
    except Exception as e:
        logger.error("portal_update_greeting: DB error: %s", e)
        raise HTTPException(503, {"error": "service temporarily unavailable"})

    return {"ok": True}


@router.patch("/kb/custom-instructions")
async def portal_update_custom_instructions(
    body: PortalCustomInstructionsRequest,
    user: UserRow = Depends(get_current_user),
):
    await get_current_user_for_kb(body.kb_id, user)

    value = body.custom_instructions.strip() if body.custom_instructions else None
    value = value or None
    if value is not None and len(value) > 2000:
        raise HTTPException(422, {"error": "custom_instructions must be at most 2000 characters"})

    kb = await get_knowledge_base(body.kb_id)
    if not kb:
        raise HTTPException(404, {"error": "kb not found"})
    if not kb.company_profile:
        raise HTTPException(400, {"error": "kb_not_ready"})

    await update_custom_instructions_kb(kb, body.kb_id, value, permanent=True)
    return {"ok": True}
