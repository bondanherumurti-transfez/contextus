# Phase 3 — Backend KB endpoints

**Repo:** `contextus`
**Status:** Ready to implement. Phase 2 (brief persistence + inbox endpoints) must be merged first.
**Unblocks:** Frontend PR 6 (KB tab read-only) and PR 7 (KB write surfaces).

This document covers two sequential PRs. They must land in order — KB read first, then KB writes.

---

## Context

The frontend knowledge base tab has three sub-tabs:
- `/knowledge-base/knowledge` — company profile + user-added Q&A list + "add Q&A" modal
- `/knowledge-base/engagement` — greeting message + quick reply pills
- `/knowledge-base/behavior` — custom instructions

All three need `GET /api/portal/kb` (PR E). The write sub-tabs additionally need PR F.

The frontend calls:
1. `GET /api/portal/kb?kb_id=<kb_id>` — full KB read, powering all three sub-tabs
2. `POST /api/portal/kb/enrich` — add one Q&A pair (wireframe 10)
3. `PATCH /api/portal/kb/pills` — update quick reply pills (wireframe 04)
4. `PATCH /api/portal/kb/greeting` — set greeting message (wireframe 04)
5. `PATCH /api/portal/kb/custom-instructions` — set custom instructions (wireframe 05)

There is also a widget-level change: `GET /api/session` must start returning `greeting` so the widget picks up portal-set greetings without needing a script attribute change.

---

## Schema prerequisites

No new tables in this phase. Verify these already landed in Phase 0 before proceeding:

```sql
-- customer_configs.greeting column (Phase 0 — 1d)
ALTER TABLE customer_configs ADD COLUMN IF NOT EXISTS greeting TEXT;
```

If the column is missing, add it now as part of PR E. It is safe to add — `IF NOT EXISTS`, no default, nullable.

---

## PR E — KB read endpoint

Read-only. No existing endpoint changes. Powers wireframes 03, 04, 05 (all three KB sub-tabs).

### New route in `backend/app/routers/portal.py`

Do not create a new file. Add to the existing portal router.

```python
@router.get("/api/portal/kb")
async def get_kb(
    kb_id: str,
    user: UserRow = Depends(get_current_user),
    _: None = Depends(lambda kb_id=kb_id, user=user: get_current_user_for_kb(kb_id, user)),
):
```

**Tenant guard:** `get_current_user_for_kb(kb_id, user)` — raises 403 if user doesn't have a row in `user_sites` for this `kb_id`. Matches the pattern from `GET /api/portal/sessions`.

### Data source

Read from the existing `customer_configs` table. This table already stores:
- `company_profile` (JSONB) — name, industry, services, out_of_scope, summary, etc.
- `pills` (JSONB array)
- `custom_instructions` (TEXT, nullable)
- `greeting` (TEXT, nullable — added in Phase 0)
- `chunks` (JSONB array) — all knowledge chunks (crawled + interview Q&A)

### Deriving `enriched_chunks`

The `chunks` array contains both crawled content and user-added Q&A pairs. User-added entries have `source` starting with `interview:`. The prefix encodes the question.

Filter and transform:

```python
def _derive_enriched_chunks(chunks: list[dict]) -> list[dict]:
    result = []
    for chunk in (chunks or []):
        source = chunk.get("source", "")
        if source.startswith("interview:"):
            question = source[len("interview:"):]
            answer = chunk.get("text") or chunk.get("content") or ""
            result.append({
                "id": chunk.get("id") or chunk.get("chunk_id") or "",
                "question": question,
                "answer": answer,
                "word_count": len(answer.split()),
            })
    return result
```

Inspect the actual `chunks` JSONB structure in the DB before writing this — field names (`id`, `text`, `source`) must match what's stored. If the chunk has a different ID field name, use that.

### Response shape

```json
{
  "kb_id": "kb_finfloo_xxx",
  "company_profile": {
    "name": "Finfloo",
    "industry": "Accounting & bookkeeping",
    "services": "Monthly bookkeeping, tax filing, payroll",
    "out_of_scope": "Investment advice",
    "summary": "Finfloo is a Jakarta-based...",
    "last_crawled_at": 1234567890,
    "pages_indexed": 12
  },
  "enriched_chunks": [
    {
      "id": "chunk_abc123",
      "question": "What are your prices for monthly bookkeeping?",
      "answer": "Starts at IDR 2.5M/month for small businesses.",
      "word_count": 9
    }
  ],
  "pills": ["Daftar sekarang", "Lihat harga", "Hubungi kami"],
  "greeting": "Halo, ada yang bisa kami bantu?",
  "custom_instructions": null
}
```

Notes:
- `company_profile` comes directly from `customer_configs.company_profile` JSONB. Add `last_crawled_at` (from `customer_configs.updated_at`) and `pages_indexed` (from `customer_configs.pages_found` if that column exists, else omit).
- `enriched_chunks` is the derived list — do **not** include the raw `chunks` array in the response.
- `pills` is `customer_configs.pills` cast to a list — empty array `[]` if null.
- `greeting` is `customer_configs.greeting` — `null` if not set.
- `custom_instructions` is `customer_configs.custom_instructions` — `null` if not set.

### Pydantic models (`models.py`)

```python
class EnrichedChunk(BaseModel):
    id: str
    question: str
    answer: str
    word_count: int

class CompanyProfileResponse(BaseModel):
    name: str | None
    industry: str | None
    services: str | None
    out_of_scope: str | None
    summary: str | None
    last_crawled_at: int | None
    pages_indexed: int | None

class KBResponse(BaseModel):
    kb_id: str
    company_profile: CompanyProfileResponse | None
    enriched_chunks: list[EnrichedChunk]
    pills: list[str]
    greeting: str | None
    custom_instructions: str | None
```

### DB helper

```python
async def db_get_kb(kb_id: str) -> dict | None:
    """
    Returns customer_configs row for kb_id, or None if not found.
    """
```

---

## PR F — KB write endpoints

Depends on PR E. Adds the four write endpoints and the `/api/session` greeting change.

All four write endpoints are new portal-scoped routes. They do **not** modify the existing admin endpoints (`PATCH /api/crawl/{kb_id}/pills`, etc.) — those stay untouched. The portal endpoints are independent duplicates that share the same underlying DB write logic.

---

### `POST /api/portal/kb/enrich`

Adds a single Q&A pair to the KB. Powers wireframe 10 (Add Q&A modal).

```python
@router.post("/api/portal/kb/enrich")
async def portal_enrich_kb(
    body: PortalEnrichRequest,
    user: UserRow = Depends(get_current_user),
    _: None = Depends(lambda body=body, user=user: get_current_user_for_kb(body.kb_id, user)),
):
```

**Request body:**

```python
class PortalEnrichRequest(BaseModel):
    kb_id: str
    question: str
    answer: str
```

**Validation (raise 422 on failure):**
- `question`: non-empty, max 200 chars
- `answer`: non-empty, max 2000 chars
- KB must be in `complete` status (check `customer_configs.status == "complete"`) — raise 400 with `{"error": "kb_not_ready"}` if not

**Rate limiting:**

Use the existing `check_rate_limit` Redis helper. Key: `enrich:{user.user_id}`. Limit: 10 per 10 minutes. On limit exceeded, return 429 with `{"error": "rate_limit_exceeded", "retry_after": <seconds>}`.

**Internal implementation:**

Construct the `answers` dict the admin endpoint expects and call the same core logic:

```python
answers = {body.question: body.answer}
# call existing enrich logic with kb_id and answers dict
```

Do not duplicate the enrichment business logic. Extract a shared `_enrich_kb(kb_id, answers)` helper that both the admin endpoint and this portal endpoint call.

**Response:** the updated `CompanyProfile` (matches existing `POST /api/crawl/{kb_id}/enrich` response).

---

### `PATCH /api/portal/kb/pills`

Updates the three quick-reply pills.

```python
@router.patch("/api/portal/kb/pills")
async def portal_update_pills(
    body: PortalPillsRequest,
    user: UserRow = Depends(get_current_user),
    _: None = Depends(lambda body=body, user=user: get_current_user_for_kb(body.kb_id, user)),
):
```

**Request body:**

```python
class PortalPillsRequest(BaseModel):
    kb_id: str
    pills: list[str]
```

**Validation:**
- Exactly 3 items
- Each non-empty string

**Implementation:** same DB write as the admin endpoint (`UPDATE customer_configs SET pills = $1 WHERE kb_id = $2`). Extract a shared `_update_pills(kb_id, pills)` helper if not already abstracted.

**Response:** `{"ok": true}` or the updated `customer_configs` row — match whatever the existing admin endpoint returns.

---

### `PATCH /api/portal/kb/greeting`

Sets the greeting message. No equivalent admin endpoint — this is net-new.

```python
@router.patch("/api/portal/kb/greeting")
async def portal_update_greeting(
    body: PortalGreetingRequest,
    user: UserRow = Depends(get_current_user),
    _: None = Depends(lambda body=body, user=user: get_current_user_for_kb(body.kb_id, user)),
):
```

**Request body:**

```python
class PortalGreetingRequest(BaseModel):
    kb_id: str
    greeting: str | None
```

**Validation:**
- If provided as a string: max 200 chars, trimmed of leading/trailing whitespace
- `null` or empty string (`""`) clears the greeting — store `NULL` in DB

**DB write:**

```sql
UPDATE customer_configs SET greeting = $1 WHERE kb_id = $2
```

Where `$1` is `None` if input is `null` or empty string after trimming.

**Response:** `{"ok": true}`

---

### `PATCH /api/portal/kb/custom-instructions`

Sets the custom instructions.

```python
@router.patch("/api/portal/kb/custom-instructions")
async def portal_update_custom_instructions(
    body: PortalCustomInstructionsRequest,
    user: UserRow = Depends(get_current_user),
    _: None = Depends(lambda body=body, user=user: get_current_user_for_kb(body.kb_id, user)),
):
```

**Request body:**

```python
class PortalCustomInstructionsRequest(BaseModel):
    kb_id: str
    custom_instructions: str | None
```

**Validation:**
- If provided as a string: max 2000 chars
- `null` clears the field
- KB must have a `company_profile` (existing rule — if `company_profile` is null, raise 400 with `{"error": "kb_not_ready"}`)

**Implementation:** same DB write as the existing admin endpoint. Extract `_update_custom_instructions(kb_id, value)` if not already a shared helper.

**Response:** `{"ok": true}` or match the existing admin endpoint's response shape.

---

### `/api/session` — add `greeting` to response

Modify the existing `GET /api/session` endpoint (in whichever router it lives — not a new route).

Add `greeting: str | None` to `SessionResponse`:

```python
class SessionResponse(BaseModel):
    # ... existing fields ...
    greeting: str | None = None  # NEW: from customer_configs.greeting
```

In the endpoint handler, after loading `customer_configs` for the session's `kb_id`, set `greeting = config.greeting` (or `None` if null).

This is an additive change — existing widget JS reads the field if present, ignores if absent. No widget code change required for the backend to ship this safely. Document in the PR that the widget JS will need a follow-up change to read this field.

---

## Pydantic models summary

Add to `models.py`:

```python
class EnrichedChunk(BaseModel):
    id: str
    question: str
    answer: str
    word_count: int

class CompanyProfileResponse(BaseModel):
    name: str | None
    industry: str | None
    services: str | None
    out_of_scope: str | None
    summary: str | None
    last_crawled_at: int | None
    pages_indexed: int | None

class KBResponse(BaseModel):
    kb_id: str
    company_profile: CompanyProfileResponse | None
    enriched_chunks: list[EnrichedChunk]
    pills: list[str]
    greeting: str | None
    custom_instructions: str | None

class PortalEnrichRequest(BaseModel):
    kb_id: str
    question: str
    answer: str

class PortalPillsRequest(BaseModel):
    kb_id: str
    pills: list[str]

class PortalGreetingRequest(BaseModel):
    kb_id: str
    greeting: str | None

class PortalCustomInstructionsRequest(BaseModel):
    kb_id: str
    custom_instructions: str | None
```

---

## Tests

### `tests/integration/test_portal_kb.py`

**GET /api/portal/kb:**
```
- Authenticated user, valid kb_id → 200 with full KB shape
- enriched_chunks contains only interview: chunks (crawled chunks excluded)
- enriched_chunks is empty list when no interview chunks exist
- question is extracted correctly (strips "interview:" prefix)
- company_profile fields match customer_configs.company_profile JSONB
- pills is [] when customer_configs.pills is null
- greeting is null when customer_configs.greeting is null
- greeting returns stored string when set
- custom_instructions returns null when not set
- kb_id not found → 404
- kb_id found but user has no access → 403
- Unauthenticated → 401
```

**POST /api/portal/kb/enrich:**
```
- Valid request → 200, Q&A added to KB, company_profile regenerated
- question empty → 422
- question > 200 chars → 422
- answer empty → 422
- answer > 2000 chars → 422
- KB not in complete status → 400 with {"error": "kb_not_ready"}
- 10th enrichment within 10 min → 200 (still under limit)
- 11th enrichment within 10 min → 429 with {"error": "rate_limit_exceeded"}
- Rate limit resets after 10 minutes
- Tenant isolation: kb_id belongs to another user → 403
- Unauthenticated → 401
```

**PATCH /api/portal/kb/pills:**
```
- Valid 3-pill array → 200, pills updated in customer_configs
- 2 pills (not 3) → 422
- 4 pills (not 3) → 422
- Empty string pill → 422
- Tenant isolation: kb_id belongs to another user → 403
- Unauthenticated → 401
```

**PATCH /api/portal/kb/greeting:**
```
- Valid greeting string → 200, customer_configs.greeting updated
- null → 200, customer_configs.greeting set to NULL
- Empty string "" → 200, customer_configs.greeting set to NULL
- greeting > 200 chars → 422
- Greeting is trimmed (leading/trailing whitespace stripped)
- Tenant isolation: kb_id belongs to another user → 403
- Unauthenticated → 401
```

**PATCH /api/portal/kb/custom-instructions:**
```
- Valid string → 200, custom_instructions updated
- null → 200, custom_instructions set to NULL
- string > 2000 chars → 422
- KB has no company_profile → 400 with {"error": "kb_not_ready"}
- Tenant isolation: kb_id belongs to another user → 403
- Unauthenticated → 401
```

**/api/session greeting:**
```
- Session response includes greeting: null when customer_configs.greeting is null
- Session response includes greeting: "..." when customer_configs.greeting is set
- Existing session response fields unchanged (no regression)
```

Mock all DB and Redis calls. No real Neon or Redis connection required.

---

## PR sequencing summary

```
Phase 0 (schema) ✅
Phase 1A (auth) ✅
Phase 1B (GET /api/portal/sites) ✅
Phase 2A (brief persistence) ✅
Phase 2B (inbox endpoints) ✅
    ↓
PR E — GET /api/portal/kb
    (read-only KB endpoint, enriched_chunks derivation)
    ↓
PR F — KB write endpoints + /api/session greeting
    (POST enrich, PATCH pills/greeting/custom-instructions, SessionResponse.greeting)
    ↓
Frontend KB tab works end-to-end (wireframes 03, 04, 05, 10)
```

---

## PR description templates

**PR E:**
> **Phase 3A — KB read endpoint**
>
> New read-only `GET /api/portal/kb` endpoint for the portal knowledge base tab (wireframes 03, 04, 05).
>
> - Returns `company_profile`, `enriched_chunks` (derived from interview: chunks), `pills`, `greeting`, `custom_instructions`
> - `enriched_chunks` pre-parses the `interview:` source prefix so the frontend renders Q&A directly
> - Tenant-isolated via `get_current_user_for_kb` — matches sessions endpoint pattern
> - No admin endpoints changed, no existing behavior affected
>
> Unblocks: PR F (KB write endpoints), frontend PR 6 (KB tab read-only).

**PR F:**
> **Phase 3B — KB write endpoints + session greeting**
>
> Four new portal write endpoints and an additive change to `/api/session`.
>
> - `POST /api/portal/kb/enrich` — add Q&A pair (rate-limited: 10/10min per user)
> - `PATCH /api/portal/kb/pills` — update 3 quick-reply pills
> - `PATCH /api/portal/kb/greeting` — set/clear greeting (stored in customer_configs.greeting)
> - `PATCH /api/portal/kb/custom-instructions` — set/clear custom instructions
> - `GET /api/session` — additive: now returns `greeting: string | null`
>
> Admin endpoints (`/api/crawl/{kb_id}/pills` etc.) are untouched. Portal endpoints share core business logic via extracted helpers.
>
> Unblocks: frontend PR 7 (KB write surfaces — pills editor, greeting editor, custom instructions editor, Add Q&A modal).

---

*Reference: `docs/BACKEND-SPEC-PORTAL-V1.md` §"Portal endpoints: GET /api/portal/kb", §"PATCH /api/portal/kb/greeting", §"Modifications to existing endpoints: /api/session". Don't add scope without updating that document and getting Bondan's sign-off.*
