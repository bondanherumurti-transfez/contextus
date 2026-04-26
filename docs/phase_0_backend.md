# Phase 0 — Backend schema + env setup

**Repo:** `contextus`
**File:** `backend/app/services/database.py` (all schema changes go here — matches existing `CREATE TABLE IF NOT EXISTS` pattern in `init_db()`)
**Status:** Ready to implement — no endpoint changes, no breaking changes to existing widget.

---

## What this phase delivers

- `users` table — portal accounts (Google OAuth identities)
- `user_sites` table — join table linking users to `kb_id`s they can access
- `briefs` table — persisted `LeadBrief` payloads (unblocks Phase 3)
- `customer_configs.greeting` column — new nullable column, additive only
- Index audit on `sessions` — two indexes required for inbox endpoint performance
- `.env.example` updated with 5 new portal env vars

No existing endpoints change. No existing tests should regress.

---

## 1. `database.py` — `init_db()` additions

Open `backend/app/services/database.py`. Find the `init_db()` function. Append the following blocks **after** all existing `CREATE TABLE IF NOT EXISTS` statements, in this order.

### 1a. `users` table

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id     TEXT PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    google_sub  TEXT UNIQUE,
    display_name TEXT,
    created_at  BIGINT NOT NULL,
    last_login_at BIGINT NOT NULL
);
```

Notes:
- `user_id` is a nanoid with `usr_` prefix, e.g. `usr_abc123` — generate at insertion time using the existing nanoid helper (or add `nanoid` import if not present)
- `google_sub` is nullable on creation because `POST /api/crawl/seed` can pre-create users by email before they ever sign in via Google
- `UNIQUE` constraint on both `email` and `google_sub` — Postgres enforces this even with nulls (only one null per unique column in Postgres; `google_sub` nulls are fine here because the constraint is deferred until the column is set)

### 1b. `user_sites` table

```sql
CREATE TABLE IF NOT EXISTS user_sites (
    user_id     TEXT NOT NULL REFERENCES users(user_id),
    kb_id       TEXT NOT NULL REFERENCES customer_configs(kb_id),
    created_at  BIGINT NOT NULL,
    PRIMARY KEY (user_id, kb_id)
);

CREATE INDEX IF NOT EXISTS idx_user_sites_user_id ON user_sites (user_id);
CREATE INDEX IF NOT EXISTS idx_user_sites_kb_id   ON user_sites (kb_id);
```

Notes:
- Composite PK `(user_id, kb_id)` prevents duplicate access rows
- No `role` column in v1 — all rows are implicitly owner-level. `role` column added in v2 when team seats land.

### 1c. `briefs` table

```sql
CREATE TABLE IF NOT EXISTS briefs (
    session_id  TEXT PRIMARY KEY REFERENCES sessions(session_id),
    kb_id       TEXT NOT NULL,
    data        JSONB NOT NULL,
    created_at  BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_briefs_kb_id ON briefs (kb_id);
```

Notes:
- `data` stores the full `LeadBrief` model JSON — no column-level normalization in v1
- `session_id` is the PK (one brief per session max)
- `kb_id` indexed for `GET /api/portal/sessions` which joins briefs by kb_id

### 1d. `customer_configs.greeting` column

```sql
ALTER TABLE customer_configs ADD COLUMN IF NOT EXISTS greeting TEXT;
```

This is the only `ALTER TABLE` in this phase. `IF NOT EXISTS` means it's safe to run on repeat `init_db()` calls. No default value — `NULL` means the widget falls back to its default greeting string.

### 1e. Index audit on `sessions`

Check whether these indexes already exist in the current `init_db()` before adding them. Search for `idx_sessions_kb_id` and `idx_sessions_updated_at` in the file. If absent, add:

```sql
CREATE INDEX IF NOT EXISTS idx_sessions_kb_id    ON sessions (kb_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions (updated_at DESC);
```

`sessions(kb_id)` is required for `GET /api/portal/sessions?kb_id=` to be performant. `sessions(updated_at DESC)` supports sorting the inbox by most-recent without a seq scan.

---

## 2. `models.py` — no changes required

The `LeadBrief` Pydantic model already exists and is used by the brief endpoint. The `briefs` table stores it as JSONB — no model changes needed in this phase.

The `SessionResponse` model will get a `greeting` field in Phase 5 (KB write endpoints). Don't add it now.

---

## 3. `.env.example` — add portal vars

Open `backend/.env.example`. Append this block after the existing variables:

```env
# ── Portal (Phase 1 — auth) ──────────────────────────────────────────────────
# All five are required when portal auth is enabled.
# Existing widget endpoints continue working when these are unset.
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=https://contextus-2d16.onrender.com/api/auth/google/callback
PORTAL_FRONTEND_URL=https://portal.getcontextus.dev
PORTAL_SESSION_SECRET=
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Do **not** add these to the live Render env yet — the auth endpoints that consume them don't exist until Phase 1. Adding them early is safe (unused vars are ignored), but coordinate with Bondan before touching the Render dashboard.

---

## 4. Tests

### New test file: `tests/unit/test_schema_migrations.py`

Create this file. It should test that `init_db()` is idempotent — running it twice does not error. Mock the asyncpg pool (same pattern as `test_third_party_resilience.py` — look at how existing tests mock `database.py`).

Minimum coverage:
- `init_db()` runs without exception on a fresh connection (use the existing mock pattern)
- `init_db()` runs without exception a second time (idempotency — `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` are safe to call repeatedly)

No credentials required. Mock everything.

---

## 5. Verification checklist

Run the existing test suite to confirm nothing regressed:

```bash
cd backend
pytest tests/integration/ -v --tb=short
pytest tests/unit/ -v --tb=short
pytest tests/e2e/test_server.py -v --tb=short
```

All pre-existing tests must pass. The new `test_schema_migrations.py` must also pass.

Manually verify the SQL by inspecting the Neon schema after deploying to staging:
```sql
\d users
\d user_sites
\d briefs
\d customer_configs   -- should show greeting column
\d sessions           -- should show idx_sessions_kb_id, idx_sessions_updated_at
```

---

## 6. PR description template

> **Phase 0 — Portal schema**
>
> Adds schema foundations for the contextus portal (v1). No endpoint changes. No existing behavior changes.
>
> **New tables:** `users`, `user_sites`, `briefs`
> **Altered:** `customer_configs` — additive `greeting TEXT` column
> **Indexes:** `sessions(kb_id)`, `sessions(updated_at DESC)` added if absent
> **Env:** `.env.example` updated with portal OAuth vars (not yet active on Render)
>
> All changes are `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` — safe to run on existing DB.
> Existing widget endpoints and tests are unaffected.
>
> Unblocks: Phase 1 (auth), Phase 3 (brief persistence)

---

## What comes next

After this PR merges to `backend-development`:

- **Phase 1 (backend)** can start: Google OAuth endpoints, session cookie, `get_current_user` dependency
- **Phase 0 (frontend)** can start in parallel: Next.js project setup, Tailwind tokens, env validation — no backend dependency

See `BACKEND-SPEC-PORTAL-V1.md` §"PR sequencing" for the full backend roadmap.
