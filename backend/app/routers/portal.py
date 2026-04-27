import base64
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import SessionDetailResponse, SessionListResponse
from app.routers.auth import get_current_user, get_current_user_for_kb
from app.services.portal_db import (
    UserRow,
    db_get_session,
    db_get_user_sites,
    db_list_sessions,
    db_user_has_kb_access,
)

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
