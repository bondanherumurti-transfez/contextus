import os
import secrets
import time
import logging
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from app.services.portal_db import (
    UserRow,
    db_create_user,
    db_get_user_by_google_sub,
    db_get_user_by_email_no_sub,
    db_get_user_by_id,
    db_set_google_sub,
    db_update_user_login,
    db_user_has_kb_access,
    db_claim_site,
    db_revoke_site,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

PORTAL_ENV_VARS = [
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
    "PORTAL_FRONTEND_URL",
    "PORTAL_SESSION_SECRET",
    "DATABASE_URL",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

SESSION_COOKIE = "contextus_portal_session"
STATE_COOKIE = "contextus_oauth_state"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
STATE_MAX_AGE = 300                   # 5 minutes


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_all_portal_env() -> None:
    missing = [v for v in PORTAL_ENV_VARS if not os.getenv(v)]
    if missing:
        raise HTTPException(
            503,
            {"error": f"Portal not configured. Missing env vars: {', '.join(missing)}"},
        )


def _is_production() -> bool:
    return os.getenv("PORTAL_FRONTEND_URL", "").startswith("https://")


def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("PORTAL_SESSION_SECRET", "")
    if not secret:
        raise HTTPException(503, {"error": "PORTAL_SESSION_SECRET not set"})
    return URLSafeTimedSerializer(secret)


# ── FastAPI dependencies ───────────────────────────────────────────────────────

async def get_current_user(request: Request) -> UserRow:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(401, {"error": "unauthenticated"})
    try:
        payload = _serializer().loads(raw, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, {"error": "unauthenticated"})

    try:
        user = await db_get_user_by_id(payload["user_id"])
    except Exception as e:
        logger.error("get_current_user: DB error: %s", e)
        raise HTTPException(503, {"error": "service temporarily unavailable"})

    if not user:
        raise HTTPException(401, {"error": "unauthenticated"})
    return user


async def get_current_user_for_kb(
    kb_id: str,
    user: UserRow = Depends(get_current_user),
) -> None:
    """Tenant isolation guard — attach to any portal endpoint that takes a kb_id."""
    try:
        has_access = await db_user_has_kb_access(user["user_id"], kb_id)
    except Exception as e:
        logger.error("get_current_user_for_kb: DB error: %s", e)
        raise HTTPException(503, {"error": "service temporarily unavailable"})

    if not has_access:
        raise HTTPException(403, {"error": "forbidden"})


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@router.get("/api/auth/google/start")
async def google_start():
    _require_all_portal_env()

    state = secrets.token_urlsafe(32)
    signed_state = _serializer().dumps({"state": state})

    params = {
        "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
        "redirect_uri": os.environ["GOOGLE_OAUTH_REDIRECT_URI"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
    }
    google_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    resp = RedirectResponse(google_url, status_code=302)
    resp.set_cookie(
        STATE_COOKIE,
        signed_state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        secure=_is_production(),
        samesite="lax",
    )
    return resp


@router.get("/api/auth/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    _require_all_portal_env()

    # User clicked "Cancel" on Google's consent screen
    if error:
        logger.info("google_callback: user cancelled or denied — error=%s", error)
        portal_url = os.getenv("PORTAL_FRONTEND_URL", "")
        resp = RedirectResponse(f"{portal_url}/login?error=auth_failed", status_code=302)
        resp.delete_cookie(STATE_COOKIE)
        return resp

    # ① Verify CSRF state
    signed_state = request.cookies.get(STATE_COOKIE)
    if not signed_state or not state:
        logger.warning("potential CSRF on auth callback — missing state cookie or param")
        raise HTTPException(400, {"error": "missing state"})
    try:
        payload = _serializer().loads(signed_state, max_age=STATE_MAX_AGE)
        if payload.get("state") != state:
            logger.warning("potential CSRF on auth callback — state mismatch")
            raise HTTPException(400, {"error": "state mismatch"})
    except (BadSignature, SignatureExpired):
        raise HTTPException(400, {"error": "invalid or expired state"})

    if not code:
        raise HTTPException(400, {"error": "missing code"})

    # ② Exchange code for tokens
    async with AsyncOAuth2Client(
        client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        redirect_uri=os.environ["GOOGLE_OAUTH_REDIRECT_URI"],
    ) as client:
        token = await client.fetch_token(GOOGLE_TOKEN_URL, code=code)

    # ③ Fetch Google userinfo
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
        resp.raise_for_status()
        info = resp.json()

    google_sub = info["sub"]
    email = info["email"]
    display_name = info.get("name")
    now = int(time.time())

    # ④ Resolve user — invite-only, lookup order matters:
    # 1. Try google_sub — covers normal returning-user case.
    # 2. If no match, try email + google_sub IS NULL — covers users pre-seeded
    #    via POST /api/admin/sites/claim before their first login.
    #    Atomically set google_sub on match to prevent this path running twice.
    # 3. Neither match → reject (not pre-seeded); redirect to not_invited.
    try:
        user = await db_get_user_by_google_sub(google_sub)
        if user:
            await db_update_user_login(user["user_id"], display_name, now)
        else:
            seeded_user = await db_get_user_by_email_no_sub(email)
            if seeded_user:
                await db_set_google_sub(seeded_user["user_id"], google_sub)
                await db_update_user_login(seeded_user["user_id"], display_name, now)
                user = seeded_user
            else:
                logger.warning("google_callback: sign-in rejected — email not pre-seeded: %s", email)
                portal_url = os.getenv("PORTAL_FRONTEND_URL", "")
                return RedirectResponse(f"{portal_url}/login?error=not_invited", status_code=302)
    except Exception as e:
        logger.error("google_callback: DB error during user upsert: %s", e)
        raise HTTPException(503, {"error": "service temporarily unavailable"})

    # ⑤ Issue session cookie
    signed_session = _serializer().dumps({"user_id": user["user_id"]})
    portal_url = os.environ["PORTAL_FRONTEND_URL"]

    response = RedirectResponse(portal_url, status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        signed_session,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=_is_production(),
        samesite="lax",
    )
    # ⑥ Clear state cookie
    response.delete_cookie(STATE_COOKIE)
    return response


@router.post("/api/auth/logout", status_code=204)
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(STATE_COOKIE)


@router.get("/api/auth/me")
async def get_me(user: UserRow = Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "display_name": user["display_name"],
    }


# ── Admin: site ownership management ──────────────────────────────────────────

def _require_admin(x_admin_secret: str | None) -> None:
    admin_secret = os.getenv("ADMIN_SECRET", "")
    if not admin_secret:
        raise HTTPException(500, {"error": "ADMIN_SECRET not configured"})
    if x_admin_secret != admin_secret:
        raise HTTPException(401, {"error": "unauthorized"})


class SiteClaimRequest(BaseModel):
    email: str
    kb_id: str


@router.post("/api/admin/sites/claim", status_code=200)
async def claim_site(
    body: SiteClaimRequest,
    x_admin_secret: str | None = Header(default=None),
):
    """Link a user (by email) to a kb_id. Creates user row if email not found."""
    _require_admin(x_admin_secret)
    try:
        await db_claim_site(body.email, body.kb_id)
    except ValueError as e:
        raise HTTPException(404, {"error": str(e)})
    return {"email": body.email, "kb_id": body.kb_id, "status": "claimed"}


@router.delete("/api/admin/sites/claim", status_code=200)
async def revoke_site(
    body: SiteClaimRequest,
    x_admin_secret: str | None = Header(default=None),
):
    """Remove a user↔kb_id link by email."""
    _require_admin(x_admin_secret)
    removed = await db_revoke_site(body.email, body.kb_id)
    return {"email": body.email, "kb_id": body.kb_id, "status": "revoked" if removed else "not_found"}
