# Phase 2 — Backend brief persistence + inbox endpoints

**Repo:** `contextus`
**Status:** Complete. Branch: `feat/phase-2-inbox`.
**Unblocks:** Frontend inbox page (wireframes 02, 08, 09).

This document covers two sequential PRs. They must land in order — brief persistence first, then inbox endpoints.

---

## Context

The frontend inbox page is already built and waiting. It calls two endpoints:

1. `GET /api/portal/sessions?kb_id=<kb_id>&limit=50` — populates the left-pane session list
2. `GET /api/portal/sessions/<session_id>` — populates the right-pane detail (brief or no-brief)

Both require briefs to be persisted to the database. Without the `briefs` table write, the inbox tag chips and the right-pane brief panel will always show the no-brief state.

The frontend handles `qualification: null` gracefully (renders no tags), but the brief detail panel (`BriefPanel`) cannot render without a persisted brief. So shipping PR C first, even before inbox endpoints, already improves the existing system — new briefs will be retrievable once PR D lands.

---

## What the frontend expects — message shape

The frontend `TranscriptMessage` component accepts `role: "user" | "bot"` and maps `"assistant"` → `"bot"` internally. The API client type in `types.ts` accepts:

```typescript
interface Message {
  role: "user" | "assistant" | "bot";
  text?: string;
  content?: string;
}
```

So the backend can return either `text` or `content` as the message field name — the frontend handles both. Use whatever the existing archived `messages` JSONB column already stores. **Do not transform or rename message fields** for the portal endpoints — return the raw JSONB as-is.

---

## Schema prerequisites

Verify these exist before writing any endpoint. They should have landed in Phase 0 (schema PR). If any are missing, add them as `IF NOT EXISTS` in `init_db()` before proceeding.

**`briefs` table** (should exist from Phase 0):
```sql
CREATE TABLE IF NOT EXISTS briefs (
    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
    kb_id      TEXT NOT NULL,
    data       JSONB NOT NULL,
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS briefs_kb_id_idx ON briefs(kb_id);
```

**`sessions` table — `contact_value` column** (check if it exists):
```sql
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS contact_value TEXT;
```

The list endpoint returns `contact_value` (the actual email/phone, not just the boolean `contact_captured`). If this column doesn't exist yet, add it here and document in the PR that existing rows will have `contact_value = NULL`.

**Indexes on `sessions`** (should exist from Phase 0 — verify):
```sql
CREATE INDEX IF NOT EXISTS sessions_kb_id_idx     ON sessions(kb_id);
CREATE INDEX IF NOT EXISTS sessions_updated_at_idx ON sessions(updated_at DESC);
```

---

## PR C — Brief persistence

Modifies `POST /api/brief/{session_id}` to write the generated brief to the `briefs` table before firing the webhook. No new endpoints. No interface changes. Pure backend durability improvement.

### Change to `POST /api/brief/{session_id}`

Current flow:
1. Load session from Redis
2. Generate brief via LLM
3. Fire webhook (fire-and-forget)
4. Mark `brief_sent = true` on the session row

New flow (insert step between 2 and 3):
1. Load session from Redis
2. Generate brief via LLM
3. **Write brief to `briefs` table** (new step)
4. Fire webhook (fire-and-forget, unchanged)
5. Mark `brief_sent = true` on the session row (unchanged)

### DB write — brief persistence

```python
async def db_save_brief(session_id: str, kb_id: str, brief_data: dict) -> None:
    """
    Upsert brief to briefs table. Called before webhook fire.
    On DB failure: log the error, do NOT re-raise — degrade gracefully
    so brief generation still returns 200 to the widget even if persistence fails.
    """
```

Important invariants:
- **DB write failure must not 500 the endpoint.** The widget fires briefs in the background; a persistence failure should be logged and swallowed, not propagated to the caller.
- **Webhook failure must not roll back the DB write.** Store brief first, fire webhook second. If the webhook fails, the brief is still safe in Neon.
- Use `ON CONFLICT (session_id) DO UPDATE SET data = EXCLUDED.data, created_at = EXCLUDED.created_at` — safe to re-run if the brief is regenerated.

### `kb_id` for the briefs row

The `briefs` table requires `kb_id` for the inbox list query's join. The existing `POST /api/brief/{session_id}` loads the session from Redis (which includes `kb_id`). Use that.

If the session is loaded from Neon (after Redis TTL expiry), `sessions.kb_id` is the source.

### Backfill note

Finfloo's existing 2 briefs are lost — they were fired to webhook and never stored. Document this in the PR. Bondan can manually re-run `POST /api/brief/{session_id}` on those session IDs to backfill. Not blocking.

### Tests for PR C

**`tests/integration/test_brief_persistence.py`**

```
Brief is written to DB on successful generation:
  - POST /api/brief/{session_id} with valid session → briefs table has a row
  - Row contains session_id, kb_id, and full brief data JSON
  - created_at is set

Webhook failure does not roll back brief:
  - Webhook URL configured but webhook call fails → brief row still present in DB
  - Response to caller is still 200 (or whatever the endpoint returned before)

DB write failure does not 500 the brief endpoint:
  - Simulate DB error in db_save_brief → endpoint still returns 200
  - Error is logged

Upsert behavior:
  - POST brief twice for same session → second write updates the row (no duplicate)

Existing brief generation tests still pass (no regressions):
  - All tests in tests/integration/test_brief.py must pass unchanged
```

---

## PR D — Inbox endpoints

Depends on PR C (brief persistence) being merged. Adds the two endpoints the frontend inbox calls.

### New file additions

Add to `backend/app/routers/portal.py` (the portal router from Phase 1). Do not create a new file.

---

### `GET /api/portal/sessions`

Lists conversations for the authenticated user's kb_id.

**Route:**
```python
@router.get("/api/portal/sessions")
async def list_sessions(
    kb_id: str,
    limit: int = 50,
    cursor: str | None = None,
    user: UserRow = Depends(get_current_user),
    _: None = Depends(lambda kb_id=kb_id, user=user: get_current_user_for_kb(kb_id, user)),
):
```

**Tenant guard:** `get_current_user_for_kb(kb_id, user)` — raises 403 if user doesn't own this kb_id.

**Query — sessions + briefs LEFT JOIN:**

```sql
SELECT
    s.session_id,
    s.created_at,
    s.updated_at,
    s.message_count,
    s.contact_captured,
    s.contact_value,
    s.messages,
    s.brief_sent,
    b.data->>'qualification'  AS qualification,
    b.data->>'quality_score'  AS quality_score
FROM sessions s
LEFT JOIN briefs b ON b.session_id = s.session_id
WHERE s.kb_id = $1
  AND ($2::TEXT IS NULL OR s.updated_at < $2::BIGINT)   -- cursor
ORDER BY s.updated_at DESC
LIMIT $3
```

Cursor encoding: base64 of the `updated_at` unix timestamp of the last item returned. Decode on the next request to get the `< X` bound. Return `next_cursor: null` when there are no more rows.

**`preview` field — derive from messages JSONB:**

Extract the first message where `role = 'user'` (or the first message of any role if no user message exists), take the first 80 characters of its text. If `messages` is empty or null, skip the session (archived sessions have at least one message by the existing archiving rule, but be defensive).

```python
def _extract_preview(messages: list[dict]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("text") or msg.get("content") or ""
            return text[:80]
    # Fallback: first message of any role
    if messages:
        msg = messages[0]
        text = msg.get("text") or msg.get("content") or ""
        return text[:80]
    return ""
```

**Response shape:**

```json
{
  "sessions": [
    {
      "session_id": "sess_xxx",
      "created_at": 1234567890,
      "updated_at": 1234567890,
      "message_count": 8,
      "contact_captured": true,
      "contact_value": "budi@example.com",
      "preview": "do you handle restaurants?",
      "qualification": "qualified",
      "quality_score": "high",
      "brief_sent": true
    }
  ],
  "next_cursor": "dXBkYXRlZF9hdA=="
}
```

`qualification` and `quality_score` are `null` when no brief exists for the session. Frontend renders no tags in that case — handle it gracefully.

**Pagination notes:**
- Default `limit` = 50, max 200. Clamp server-side.
- `next_cursor` is `null` when `len(sessions) < limit` (no more pages).
- Empty sessions array (no conversations) → `{"sessions": [], "next_cursor": null}` — frontend renders wireframe 08.

---

### `GET /api/portal/sessions/{session_id}`

Full detail for a single session. Powers wireframes 02 (with brief) and 09 (without brief).

**Route:**
```python
@router.get("/api/portal/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    user: UserRow = Depends(get_current_user),
):
```

**Tenant guard (different pattern — session_id, not kb_id):**

Load the session from DB first, then verify `session.kb_id` is in the user's `user_sites`. Do NOT use `get_current_user_for_kb` directly — the client doesn't pass `kb_id` here.

```python
session = await db_get_session(session_id)
if not session:
    raise HTTPException(404, {"error": "session not found"})

has_access = await db_user_has_kb_access(user["user_id"], session["kb_id"])
if not has_access:
    raise HTTPException(403, {"error": "forbidden"})
```

This is critical for tenant isolation. A user with a valid session cookie must not be able to fetch another user's sessions by guessing session IDs.

**Query:**

```sql
SELECT
    s.session_id,
    s.kb_id,
    s.created_at,
    s.updated_at,
    s.message_count,
    s.messages,
    s.contact_captured,
    s.contact_value,
    s.brief_sent,
    b.data AS brief_data
FROM sessions s
LEFT JOIN briefs b ON b.session_id = s.session_id
WHERE s.session_id = $1
```

**Response shape:**

```json
{
  "session": {
    "session_id": "sess_xxx",
    "kb_id": "kb_finfloo_xxx",
    "created_at": 1234567890,
    "updated_at": 1234567890,
    "message_count": 8,
    "messages": [
      { "role": "bot", "text": "halo, ada yang bisa kami bantu?" },
      { "role": "user", "text": "do you handle restaurants?" }
    ],
    "contact_captured": true,
    "contact_value": "budi@example.com",
    "brief_sent": true
  },
  "brief": null
}
```

Return `messages` as-is from the `messages` JSONB column. Do not transform role names or field names. The frontend handles `"assistant"` and `"bot"` both.

`brief` is `null` when no row exists in `briefs` for this `session_id`. Frontend renders `NoBriefPanel` in that case.

When `brief` is present:

```json
{
  "brief": {
    "who": "restaurant owner, 3 outlets",
    "need": "monthly bookkeeping + tax",
    "signals": "has budget, timeline this month",
    "open_questions": "...",
    "suggested_approach": "...",
    "quality_score": "high",
    "qualification": "qualified",
    "qualification_reason": "...",
    "scope_match": "...",
    "red_flags": [],
    "contact": { "email": "budi@example.com" },
    "created_at": "2026-04-25T14:32:00Z"
  }
}
```

This is the raw `briefs.data` JSONB — return it directly, no reshaping needed.

---

### Models (`models.py`)

```python
from pydantic import BaseModel
from typing import Any

class SessionListItem(BaseModel):
    session_id: str
    created_at: int
    updated_at: int
    message_count: int
    contact_captured: bool
    contact_value: str | None
    preview: str
    qualification: str | None
    quality_score: str | None
    brief_sent: bool

class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]
    next_cursor: str | None

class SessionDetailData(BaseModel):
    session_id: str
    kb_id: str
    created_at: int
    updated_at: int
    message_count: int
    messages: list[dict]
    contact_captured: bool
    contact_value: str | None
    brief_sent: bool

class SessionDetailResponse(BaseModel):
    session: SessionDetailData
    brief: dict[str, Any] | None
```

---

### DB helpers

Add to `portal_db.py` (or `database.py` — match the existing pattern):

```python
async def db_list_sessions(
    kb_id: str,
    limit: int,
    cursor_updated_at: int | None,
) -> list[dict]:
    """
    Returns sessions for a kb_id with brief join, sorted updated_at DESC.
    cursor_updated_at: if set, returns only sessions with updated_at < cursor_updated_at.
    """

async def db_get_session(session_id: str) -> dict | None:
    """
    Returns full session row + brief data (or None for brief if not found).
    Used by GET /api/portal/sessions/{id}.
    """
```

---

### Tests for PR D

**`tests/integration/test_portal_sessions.py`**

```
List endpoint:
  - Authenticated user with sessions → 200, sessions listed newest first
  - Authenticated user with no sessions → 200, {"sessions": [], "next_cursor": null}
  - Sessions with briefs → qualification and quality_score populated
  - Sessions without briefs → qualification: null, quality_score: null
  - preview is the first user message, truncated to 80 chars
  - preview falls back to first message of any role when no user message exists
  - Pagination: limit=2 returns 2 items + next_cursor
  - Pagination: second page with cursor returns next 2 items
  - Pagination: last page has next_cursor: null
  - kb_id missing → 422

Detail endpoint:
  - Valid session_id, user owns the kb_id → 200 with session + brief (or null)
  - brief: null when no briefs row exists
  - brief populated when briefs row exists
  - messages returned as-is from JSONB (not transformed)
  - session_id not found → 404
  - session_id found but belongs to another user's kb_id → 403
  - Unauthenticated → 401

TENANT ISOLATION — required, block PR until passing:
  - User A has session sess_A (kb_id = kb_A). User B authenticated.
  - GET /api/portal/sessions?kb_id=kb_A with User B's cookie → 403
  - GET /api/portal/sessions/{sess_A} with User B's cookie → 403
  - User A cannot see User B's sessions in their list (separate kb_ids)
  - Unauthenticated request to either endpoint → 401
```

Mock all DB calls. No real Neon connection or Redis required.

---

## PR sequencing summary

```
Phase 0 (schema) ✅
Phase 1A (auth) ✅
Phase 1B (GET /api/portal/sites) ✅
    ↓
PR C — brief persistence
    (POST /api/brief/{id} writes to briefs table)
    ↓
PR D — inbox endpoints
    (GET /api/portal/sessions, GET /api/portal/sessions/{id})
    ↓
Frontend inbox works end-to-end (wireframes 02, 08, 09)
```

---

## PR description templates

**PR C:**
> **Phase 2A — Brief persistence**
>
> Modifies `POST /api/brief/{session_id}` to write the generated brief to the `briefs` table before firing the webhook. No new endpoints. No interface changes.
>
> - `db_save_brief()` upserts to `briefs(session_id, kb_id, data, created_at)`
> - DB write failure is logged and swallowed — endpoint still returns 200
> - Webhook failure does not roll back the DB write
> - Existing brief generation tests still pass
>
> Unblocks: PR D (inbox endpoints), which joins briefs on session list + detail.

**PR D:**
> **Phase 2B — Inbox endpoints**
>
> Two read-only portal endpoints powering the inbox (wireframes 02, 08, 09).
>
> - `GET /api/portal/sessions` — lists sessions for a kb_id, LEFT JOINs briefs for qualification/score tags
> - `GET /api/portal/sessions/{session_id}` — returns full session with messages + brief (or null)
> - Cursor-based pagination (base64 updated_at) on the list endpoint
> - Tenant isolation: list endpoint uses `get_current_user_for_kb`; detail endpoint loads session then checks `session.kb_id` against `user_sites`
> - `contact_value` column added to `sessions` if not already present
>
> Unblocks: frontend inbox page (`src/app/(authenticated)/inbox/page.tsx`).

---

*Reference: `docs/BACKEND-SPEC-PORTAL-V1.md` §"Portal endpoints: GET /api/portal/sessions", §"Brief persistence", §"Tests". Don't add scope without updating that document and getting Bondan's sign-off.*
