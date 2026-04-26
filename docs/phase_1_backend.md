# Phase 1 — Backend auth + sites endpoint

**Repo:** `contextus`
**Status:** Complete. Branch: `feat/auth`.
**Unblocks:** Frontend Phase 1 (auth shell) and Phase 2 (sites page).

This document covers two sequential PRs. They must land in order — auth first, then sites.

---

## PR A — Auth flow

Everything the portal needs to authenticate users and protect endpoints.

### New dependency: `authlib`

```bash
pip install authlib
```

Add to `backend/requirements.txt`.

### New file: `backend/app/routers/auth.py`

Create this file. It owns all four auth endpoints and the two FastAPI dependencies.

---

#### Dependencies (implement these first — endpoints below use them)

**`get_current_user(request: Request) -> UserRow`**

```python
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException

async def get_current_user(request: Request) -> UserRow:
    secret = _require_portal_env("PORTAL_SESSION_SECRET")
    serializer = URLSafeTimedSerializer(secret)

    raw = request.cookies.get("contextus_portal_session")
    if not raw:
        raise HTTPException(401, {"error": "unauthenticated"})

    try:
        # max_age 30 days in seconds
        payload = serializer.loads(raw, max_age=60 * 60 * 24 * 30)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, {"error": "unauthenticated"})

    user = await db_get_user_by_id(payload["user_id"])
    if not user:
        raise HTTPException(401, {"error": "unauthenticated"})

    return user
```

`itsdangerous` is already a Starlette transitive dependency — no new install needed.

**`get_current_user_for_kb(kb_id: str, user: UserRow = Depends(get_current_user)) -> None`**

```python
async def get_current_user_for_kb(
    kb_id: str,
    user: UserRow = Depends(get_current_user),
) -> None:
    has_access = await db_user_has_kb_access(user["user_id"], kb_id)
    if not has_access:
        raise HTTPException(403, {"error": "forbidden"})
```

This is the **tenant isolation guard**. Every portal endpoint that takes a `kb_id` (as path param, query param, or request body) calls this dependency. Never skip it. Cross-tenant data leakage is the worst possible bug class.

---

#### `GET /api/auth/google/start`

```python
@router.get("/api/auth/google/start")
async def google_start(response: Response):
    _require_all_portal_env()

    state = secrets.token_urlsafe(32)

    # Store state in a signed short-lived cookie (5 min TTL)
    serializer = URLSafeTimedSerializer(os.environ["PORTAL_SESSION_SECRET"])
    signed_state = serializer.dumps({"state": state})

    redirect_uri = _build_google_oauth_url(state)

    resp = RedirectResponse(redirect_uri, status_code=302)
    resp.set_cookie(
        "contextus_oauth_state",
        signed_state,
        max_age=300,       # 5 minutes
        httponly=True,
        secure=_is_production(),
        samesite="lax",
    )
    return resp
```

No JSON body. Pure 302 redirect to Google's authorization URL with scopes `openid email profile`.

---

#### `GET /api/auth/google/callback`

Steps in order:
1. Verify `state` param against the signed `contextus_oauth_state` cookie. Mismatch or missing → 400, log `"potential CSRF on auth callback"`.
2. Exchange `code` for tokens via Authlib.
3. Fetch Google's userinfo endpoint (`https://openidconnect.googleapis.com/v1/userinfo`) with the access token.
4. Look up `users` table by `google_sub`:
   - **Found:** update `last_login_at` and `display_name`.
   - **Not found by `google_sub`:** check `email` AND `google_sub IS NULL` (handles the seed-before-login case from `POST /api/crawl/seed`). If found this way, **atomically** set `google_sub` on the row.
   - **Neither match:** insert a new user row (nanoid `usr_` prefix for `user_id`).
5. Issue `contextus_portal_session` cookie (signed, HTTP-only, 30-day max age).
6. Clear the `contextus_oauth_state` cookie.
7. Redirect to `PORTAL_FRONTEND_URL`.

Cookie settings for `contextus_portal_session`:
```python
response.set_cookie(
    "contextus_portal_session",
    signed_payload,
    max_age=60 * 60 * 24 * 30,   # 30 days
    httponly=True,
    secure=_is_production(),
    samesite="lax",
)
```

**Important — seed-then-login matching logic.** Document this in code comments:
```python
# Lookup order matters:
# 1. Try google_sub — covers the normal returning-user case.
# 2. If no match, try email AND google_sub IS NULL — covers users pre-created
#    via POST /api/crawl/seed with owner_email before they first logged in.
#    Atomically update google_sub on match to prevent this path running twice.
# 3. If google_sub IS NOT NULL and doesn't match on step 1 — treat as new user.
#    Different Google account at same email is theoretically possible; be safe.
```

---

#### `POST /api/auth/logout`

Clears both portal cookies and returns 204:
```python
@router.post("/api/auth/logout", status_code=204)
async def logout(response: Response):
    response.delete_cookie("contextus_portal_session")
    response.delete_cookie("contextus_oauth_state")
```

---

#### `GET /api/auth/me`

```python
@router.get("/api/auth/me")
async def get_me(user: UserRow = Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "display_name": user["display_name"],
    }
```

Returns 401 (via `get_current_user`) if unauthenticated. Used by the frontend on every page load to verify session validity.

---

### Register router in `backend/app/main.py`

```python
from app.routers import auth
app.include_router(auth.router)
```

Mount at root (no prefix) — the routes themselves are already `/api/auth/*`.

### CORS update in `main.py`

Add `PORTAL_FRONTEND_URL` to the `allow_origins` list. Also allow the Vercel preview URL pattern for PR testing:

```python
origins = [
    os.getenv("ALLOWED_ORIGINS", "").split(","),   # existing
    os.getenv("PORTAL_FRONTEND_URL", ""),
    # Vercel preview deploys — needed for frontend PR testing
    # Pattern: https://contexts-portal-*.vercel.app
    # Add as an allow_origin_regex if FastAPI's CORSMiddleware supports it,
    # or enumerate the specific preview URL when testing.
]
```

Must also set `allow_credentials=True` on `CORSMiddleware` — cookie-based auth requires this.

---

### DB helpers needed (add to `database.py` or a new `portal_db.py`)

```python
async def db_get_user_by_id(user_id: str) -> UserRow | None
async def db_get_user_by_google_sub(google_sub: str) -> UserRow | None
async def db_get_user_by_email_no_sub(email: str) -> UserRow | None  # email + google_sub IS NULL
async def db_create_user(email, google_sub, display_name) -> UserRow
async def db_update_user_login(user_id, display_name, last_login_at) -> None
async def db_set_google_sub(user_id, google_sub) -> None              # atomic update for seed path
async def db_user_has_kb_access(user_id: str, kb_id: str) -> bool
```

---

### Helper: `_require_all_portal_env()`

If any of the 5 portal env vars are missing, the auth endpoints should return **503** with a message pointing to the missing variable — not 500. The widget endpoints must keep working regardless.

```python
PORTAL_ENV_VARS = [
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
    "PORTAL_FRONTEND_URL",
    "PORTAL_SESSION_SECRET",
]

def _require_all_portal_env():
    missing = [v for v in PORTAL_ENV_VARS if not os.getenv(v)]
    if missing:
        raise HTTPException(
            503,
            {"error": f"Portal not configured. Missing: {', '.join(missing)}"}
        )
```

---

### Models (`backend/app/models.py`)

Add:
```python
class UserResponse(BaseModel):
    user_id: str
    email: str
    display_name: str | None
```

---

### Tests for PR A

**`tests/integration/test_auth.py`**

Cover:
- `GET /api/auth/google/start` — returns 302, sets `contextus_oauth_state` cookie, redirects to Google URL with correct params
- `GET /api/auth/google/callback` — valid code + state → session cookie set, redirect to `PORTAL_FRONTEND_URL`
- `GET /api/auth/google/callback` — state mismatch → 400
- `GET /api/auth/google/callback` — missing state cookie → 400
- `GET /api/auth/google/callback` — new user → inserted into `users`
- `GET /api/auth/google/callback` — returning user → `last_login_at` updated, not duplicated
- `GET /api/auth/google/callback` — seed-then-login path: pre-created user with `google_sub IS NULL` gets `google_sub` set on first login
- `GET /api/auth/me` — valid session cookie → 200 with user profile
- `GET /api/auth/me` — no cookie → 401
- `GET /api/auth/me` — tampered cookie → 401
- `GET /api/auth/me` — expired cookie (mock `itsdangerous` to simulate expiry) → 401
- `POST /api/auth/logout` — clears cookie, returns 204
- Any auth endpoint — missing portal env vars → 503

**`tests/unit/test_auth_dependency.py`**

Cover the FastAPI dependencies in isolation (no HTTP layer):
- `get_current_user` — valid signed cookie → returns user
- `get_current_user` — invalid signature → raises 401
- `get_current_user` — expired signature → raises 401
- `get_current_user` — cookie missing → raises 401
- `get_current_user_for_kb` — user has access → no exception
- `get_current_user_for_kb` — user doesn't have access → raises 403

Mock all DB calls. No credentials required.

---

## PR B — Sites endpoint

Depends on PR A being merged. Adds `GET /api/portal/sites`.

### New file: `backend/app/routers/portal.py`

All portal endpoints live here. Mount it in `main.py` at `/api/portal`.

```python
from fastapi import APIRouter, Depends
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/portal")
```

---

#### `GET /api/portal/sites`

```python
@router.get("/api/portal/sites")
async def list_sites(user: UserRow = Depends(get_current_user)):
    sites = await db_get_user_sites(user["user_id"])
    return {"sites": sites}
```

Response shape per site:
```json
{
  "kb_id": "kb_finfloo_xxx",
  "url": "https://finfloo.com",
  "name": "Finfloo",
  "token": "kb_finfloo_xxx",
  "created_at": 1234567890,
  "last_crawled_at": 1234567890,
  "pages_indexed": 12
}
```

**Field sources:**

| Field | Source |
|---|---|
| `kb_id` | `user_sites.kb_id` |
| `url` | `customer_configs.url` (or the original crawl URL from `knowledge_bases`) |
| `name` | `knowledge_bases.company_profile->>'name'` — fallback to `url` if null or KB not found |
| `token` | `kb_id` — the widget embed snippet uses `data-knowledge-base-id` which is the `kb_id`. No separate token in v1. |
| `created_at` | `user_sites.created_at` |
| `last_crawled_at` | `knowledge_bases.updated_at` — null if KB not yet crawled |
| `pages_indexed` | `knowledge_bases.pages_found` — 0 or null if not crawled |

**Implementation note:** pre-compose in a single SQL query rather than N+1 lookups. Example:

```sql
SELECT
    us.kb_id,
    cc.url,
    kb.company_profile->>'name' AS name,
    us.created_at,
    kb.updated_at AS last_crawled_at,
    kb.pages_found AS pages_indexed
FROM user_sites us
LEFT JOIN customer_configs cc ON cc.kb_id = us.kb_id
LEFT JOIN knowledge_bases kb  ON kb.kb_id = us.kb_id
WHERE us.user_id = $1
ORDER BY us.created_at DESC
```

Verify the actual column names in `database.py` before writing this query — particularly `knowledge_bases.updated_at` (may be named differently) and `customer_configs.url`.

**Empty array is valid.** A user with no rows in `user_sites` gets `{"sites": []}` — frontend renders wireframe 07 (first-time user). Return 200, not 404.

---

### Model (`models.py`)

Add:
```python
class SiteItem(BaseModel):
    kb_id: str
    url: str | None
    name: str | None
    token: str
    created_at: int
    last_crawled_at: int | None
    pages_indexed: int | None

class SitesResponse(BaseModel):
    sites: list[SiteItem]
```

---

### DB helper

```python
async def db_get_user_sites(user_id: str) -> list[dict]
```

Runs the join query above. Returns a list of dicts matching `SiteItem`. Falls back gracefully if `knowledge_bases` row doesn't exist for a `kb_id` (LEFT JOIN handles this — return nulls for KB fields).

---

### Register portal router in `main.py`

```python
from app.routers import portal
app.include_router(portal.router)
```

---

### Tests for PR B

**`tests/integration/test_portal_sites.py`**

Required coverage — all of these must pass before the PR merges:

```
Authenticated user with one site:
  - GET /api/portal/sites → 200, list contains the site with correct fields

Authenticated user with multiple sites:
  - GET /api/portal/sites → 200, list contains all sites, ordered by created_at DESC

Authenticated user with no sites (new user):
  - GET /api/portal/sites → 200, {"sites": []}

Unauthenticated request:
  - GET /api/portal/sites → 401

TENANT ISOLATION — required, block PR until passing:
  - User A authenticated, calls GET /api/portal/sites
  - Response contains only User A's sites, not User B's sites
  - Even if User B has sites with the same kb_id pattern, they don't appear

Field shape:
  - kb_id is a string
  - token equals kb_id
  - name falls back to url when company_profile.name is null
  - last_crawled_at is null when knowledge_bases row doesn't exist
  - pages_indexed is null when knowledge_bases row doesn't exist
```

Mock the DB. No real Neon connection required.

---

## PR sequencing summary

```
Phase 0 (schema) ✅
    ↓
PR A — auth flow, get_current_user + get_current_user_for_kb, /api/auth/* endpoints
    ↓
PR B — GET /api/portal/sites, portal router, SiteItem model
    ↓
Frontend Phase 1 (auth shell) can wire up end-to-end
Frontend Phase 2 (sites page) can wire up end-to-end
```

---

## PR description templates

**PR A:**
> **Phase 1 — Portal auth**
>
> Google OAuth flow for the contextus portal. HTTP-only signed session cookie, `get_current_user` and `get_current_user_for_kb` FastAPI dependencies.
>
> - New endpoints: `GET /api/auth/google/start`, `GET /api/auth/google/callback`, `POST /api/auth/logout`, `GET /api/auth/me`
> - Cookie: `contextus_portal_session` — signed with `itsdangerous`, 30-day max age, HTTP-only
> - Seed-then-login path: users pre-created via `crawl/seed owner_email` get `google_sub` set on first login
> - Auth endpoints return 503 (not 500) when portal env vars are missing; widget endpoints unaffected
> - CORS: `PORTAL_FRONTEND_URL` added to `allow_origins`; `allow_credentials=True`
>
> Unblocks: PR B (sites endpoint), frontend auth shell.

**PR B:**
> **Phase 2 — GET /api/portal/sites**
>
> First portal data endpoint. Lists all sites a user has access to via `user_sites` join.
>
> - Single SQL join across `user_sites`, `customer_configs`, `knowledge_bases`
> - Empty array for users with no sites (first-time user flow)
> - `token` field = `kb_id` for v1 embed snippet
> - Tenant isolation: each user sees only their own sites
>
> Unblocks: frontend sites page (wireframes 06 and 07).

---

*Reference: `docs/BACKEND-SPEC-PORTAL-V1.md` §"Auth flow", §"Portal endpoints: GET /api/portal/sites", §"Tests". Don't add scope without updating that document and getting Bondan's sign-off.*
