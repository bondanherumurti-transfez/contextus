# contextus

**From Contact Us to contextus.**

An embeddable AI chat widget that replaces traditional contact forms with intelligent, lead-qualifying conversations. Every chat becomes a structured lead brief — who the visitor is, what they need, their urgency signals, and a suggested follow-up.

Live: [www.getcontextus.dev](https://www.getcontextus.dev)
Backend API: [contextus-2d16.onrender.com](https://contextus-2d16.onrender.com)

---

## Status

**Phase 1 — Widget frontend: complete.**
Vanilla JS widget, 11 states, iframe embed, postMessage communication.

**Phase 2 — Backend API: complete.**
FastAPI backend with OpenRouter LLM integration, web crawler (httpx + Firecrawl fallback), Redis storage, SSE streaming. Live on Render.

**Phase 3 — /try page: complete.**
Interactive demo page — paste any URL, crawl it in real time, chat with the resulting AI assistant, and generate a lead brief. Fully wired to the real backend.

**Phase 3.5 — Observability: complete.**
Distributed tracing with OpenTelemetry + Honeycomb. Traces LLM calls, crawler performance, and end-to-end chat latency.

**Phase 3.6 — Widget tests + Analytics: complete.**
Playwright end-to-end tests covering phase transitions, animation behavior, and dynamic sizing. Vercel Web Analytics added to all frontend pages. GitHub Actions CI runs on every `widget/**` change.

**Phase 3.7 — Floating widget: complete.**
New embeddable floating chat widget (FAB + panel) built in vanilla JS with Shadow DOM isolation. Wired to the real backend via SSE streaming. Mobile-first with dark theme, virtual keyboard handling, and iOS auto-zoom prevention. 54 Playwright tests.

**Phase 3.9 — Bubbles appearance: complete.**
New `data-appearance="bubbles"` mode — pill-shaped quick-reply buttons float above the FAB before the panel is opened. Staggered entrance animation, session-driven pill refresh, one-way gate once conversation starts. 15 new Playwright tests.

**Phase 3.10 — Session archiving: complete.**
Non-empty chat sessions are now archived to Neon Postgres on every conversation turn via write-through from Redis. `brief_sent` is marked in Neon after brief generation. Redis TTLs unchanged — Neon is the persistent analysis layer. 8 new backend tests.

**Phase 3.8 — Test hardening: complete.**
Backend unit + resilience tests (41 new), widget backend error handling tests (17 new), and GitHub Actions CI for the backend. No credentials required — all third-party calls mocked.

---

## Project structure

```
contextus/
├── index.html                          # Landing page (Vercel)
├── join/
│   └── index.html                      # /join waitlist page
├── try/
│   └── index.html                      # /try demo page — real backend wired
├── widget/
│   ├── widget.html                     # Standalone iframe shell
│   ├── widget.js                       # Widget component (vanilla JS, 11-state machine)
│   ├── widget.css                      # Widget styles
│   ├── floating.js                     # Floating chat widget (Shadow DOM, FAB + panel)
│   ├── floating-demo.html              # Floating widget local demo page
│   ├── floating-bubbles-demo.html      # Bubbles appearance fixture (Playwright tests)
│   ├── embed.js                        # Tier 2 inject script (placeholder)
│   └── tests/
│       ├── widget.spec.ts              # Playwright e2e tests — iframe widget (31 tests)
│       ├── floating.spec.ts            # Playwright e2e tests — floating widget (77 tests)
│       └── helpers/
│           └── mock-api.ts             # Route mock helpers (session, chat, hang, complete)
├── assets/
│   ├── contextus-logo-dark.svg
│   ├── contextus-logo-light.svg
│   └── contextus-logo-lockup.svg
├── docs/
│   ├── backend-plan.md
│   └── contextus-widget-design-guideline.html
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI app, CORS, router mount
│   │   ├── models.py                   # Pydantic models
│   │   ├── routers/
│   │   │   ├── crawl.py                # Crawl + demo KB endpoints
│   │   │   ├── session.py              # Session endpoints
│   │   │   ├── chat.py                 # Chat endpoint (SSE)
│   │   │   └── brief.py                # Lead brief endpoint
│   │   └── services/
│   │       ├── redis.py                # Upstash Redis client
│   │       ├── crawler.py              # Web crawler (httpx + Firecrawl fallback)
│   │       ├── chunker.py              # Text chunking
│   │       ├── retrieval.py            # Keyword-based retrieval
│   │       ├── llm.py                  # OpenRouter LLM wrapper
│   │       └── telemetry.py            # OpenTelemetry + Honeycomb tracing
│   ├── tests/
│   │   ├── integration/
│   │   │   ├── test_crawl.py           # Crawl endpoint tests (mocked Redis)
│   │   │   ├── test_brief.py           # Brief + webhook dispatch tests (10 tests)
│   │   │   ├── test_chat.py
│   │   │   ├── test_session.py
│   │   │   └── test_health.py
│   │   ├── unit/
│   │   │   ├── test_select_pills.py    # select_pills() logic (13 tests)
│   │   │   └── test_third_party_resilience.py  # Upstash/Neon/Firecrawl/OpenRouter failure modes (28 tests)
│   │   └── e2e/
│   │       ├── test_server.py          # Real uvicorn subprocess (no credentials needed)
│   │       └── test_real_pipeline.py   # Live Redis + LLM (skipped in CI)
│   ├── requirements.txt
│   ├── render.yaml
│   └── .env.example
├── package.json                        # Playwright test runner (devDependency only)
├── playwright.config.ts                # Playwright config — Chromium, serves repo root
├── .github/
│   └── workflows/
│       ├── widget-tests.yml            # CI: Playwright tests on push/PR to widget/**
│       └── backend-tests.yml           # CI: pytest integration + E2E server on push/PR to backend/**
└── vercel.json                         # Vercel headers config (iframe embedding)
```

---

## /try page

The `/try` page at `/try/index.html` is a full end-to-end demo:

1. **Paste a URL** — crawls the site in the background (real API call)
2. **Summary card** — shows the extracted company profile (name, industry, services, gaps)
3. **Chat** — opens the real widget in an iframe, wired to the crawled knowledge base
4. **Lead brief** — after 3+ messages, generates a structured brief from the conversation
5. **Empty state** — if the site can't be crawled, a manual form lets users fill in their business info

### States
`idle → crawling → summary → chat → brief`
`idle → crawling → empty (thin/unscrapable site) → manual form → summary → chat → brief`

### postMessage events
| Event | Direction | Payload |
|-------|-----------|---------|
| `contextus:session_ready` | widget → parent | `{ session_id }` |
| `contextus:message_sent` | widget → parent | `{}` |
| `contextus:resize` | widget → parent | `{ height }` |
| `contextus:expand` | widget → parent | `{}` — triggers wrapper expansion and scroll |

---

## Widget

### Floating widget (Tier 2 — script tag)

A self-contained floating chat button (FAB) + slide-up panel, injected via a single `<script>` tag. Uses Shadow DOM for full CSS isolation from the host site.

```html
<script
  src="https://www.getcontextus.dev/widget/floating.js"
  data-contextus-id="my-widget"
  data-knowledge-base-id="YOUR_KB_ID"
></script>
```

**Features:**
- Shadow DOM — host site styles cannot bleed in or out
- Eager session init — fetches brand name and KB-specific pills on page load (no cold start on first message)
- SSE streaming — token-by-token response from the backend
- Mobile dark theme — full-screen panel with `#1a1a1a` background
- Virtual keyboard handling — `ctxf-kbd` class hides header/messages so input covers the panel (Intercom-style) when keyboard opens; removed on blur
- iOS auto-zoom prevention — input `font-size` pinned at 16px
- Body scroll lock — saves/restores scroll position; no page jump on open/close
- `window.visualViewport` adjustment — panel resizes to exact visible area when keyboard is open

**Script tag attributes:**

| Attribute | Description |
|-----------|-------------|
| `data-contextus-id` | Widget instance ID |
| `data-knowledge-base-id` | KB ID from crawl, or `demo` |
| `data-greeting` | Custom greeting message |
| `data-name` | Widget header name (overridden by KB name from session API) |
| `data-lang` | Language override (`en`, `id`) |
| `data-auto-open` | Set to `"1"` to open on load |
| `data-appearance` | Set to `"bubbles"` to enable floating quick-reply pills above the FAB |

**JS API (via `window.contextus`):**

```js
window.contextus.open()
window.contextus.close()
window.contextus.toggle()
window.contextus.setBadge(3)
window.contextus.clearBadge()
window.contextus.on('open',    () => {})
window.contextus.on('close',   () => {})
window.contextus.on('message', ({ role, text }) => {})
```

---

### Embedding (Tier 1 — iframe)

```html
<style>
  #contextus-wrapper {
    max-height: 250px;
    overflow: hidden;
    transition: max-height 0.35s ease;
  }
  #contextus-wrapper.expanded { max-height: 520px; }
  #contextus-iframe { border: none; display: block; width: 100%; }
  #contextus-wrapper.expanded #contextus-iframe { height: 480px; }
</style>

<div id="contextus-wrapper">
  <iframe id="contextus-iframe"
    src="https://www.getcontextus.dev/widget/widget.html?knowledgeBaseId=YOUR_KB_ID&apiUrl=https://contextus-2d16.onrender.com&dynamicHeight=1"
    frameborder="0"></iframe>
</div>

<script>
  window.addEventListener('message', function(e) {
    if (e.data.type === 'contextus:resize') {
      var iframe = document.getElementById('contextus-iframe');
      if (iframe && !iframe.dataset.expanded && e.data.height)
        iframe.style.height = e.data.height + 'px';
    }
    if (e.data.type === 'contextus:expand') {
      var wrapper = document.getElementById('contextus-wrapper');
      if (wrapper) {
        wrapper.classList.add('expanded');
        var iframe = wrapper.querySelector('iframe');
        if (iframe) { iframe.dataset.expanded = '1'; iframe.style.height = ''; }
        setTimeout(function() {
          wrapper.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 50);
      }
    }
  });
</script>
```

### URL parameters

| Param | Values | Description |
|---|---|---|
| `apiUrl` | URL | Backend API base URL |
| `knowledgeBaseId` | string | Job ID from crawl, or `demo` for the contextus demo KB |
| `name` | string | Widget header name |
| `greeting` | string | Input placeholder text |
| `lang` | `auto`, `en`, `id` | Language override |
| `transparent` | `0`, `1` | Transparent widget background |
| `dynamicHeight` | `0`, `1` | Enable postMessage height resize |

### 11 widget states

| # | State | Description |
|---|---|---|
| 1 | idle | Header + input + pills. No messages. |
| 2 | visitor-typing | Text in input. Send button turns active. |
| 3 | agent-thinking | Message sent. Typing dots. Input disabled. |
| 4 | active | Multi-turn conversation. |
| 5 | scroll | Messages overflow max-height. Internal scroll. |
| 6 | boundary | Agent hits knowledge limit. Amber banner. |
| 7 | contact | Contact info captured. Lead brief starts. |
| 8 | idle-nudge | 60s silence. Single muted italic nudge. |
| 9 | error | Network/LLM timeout. Red banner. Auto-retries once after 2s. |
| 10 | returning | Previous conversation shown at 55% opacity with label. |
| 11 | complete | Sign-off message. Soft-reset after 30s. |

---

## Widget Tests

End-to-end tests with [Playwright](https://playwright.dev/) — runs against a local static file server (`serve .`), all API calls mocked. No backend required.

### Run locally

```bash
npm install
npx playwright install chromium
npm test
```

### Test coverage

**Iframe widget — `widget.spec.ts` (31 tests)**

| Group | Tests |
|-------|-------|
| Phase 1 — idle state | Pills visible, max-width ≤600px, send button states |
| Phase 1 → Phase 2 transition | `ctx-expanded` class, `contextus:expand` postMessage, pills hidden, messages visible |
| Animation behavior | Typing dots visible, `ctx-dot-pulse` animation, staggered delays, send button disabled during stream |
| Dynamic sizing | Height expands after transition, dynamicHeight param works |
| Complete phase | Banner shown + input disabled after conversation ends, WAITLIST_COMPLETE stripped |
| Pill interaction | Clicking pill triggers phase transition |
| Backend error handling | Session 500/abort, chat 500 both attempts, dots removed, input re-enabled, error placeholder, retry-and-succeed, silent retry |

**Floating widget — `floating.spec.ts` (77 tests)**

| Group | Tests |
|-------|-------|
| FAB visibility & position | Visible on load, bottom-right position, 56×56px size |
| Panel initial state | No `ctxf-open` on load, not visible before FAB click |
| Open / close | FAB click opens, close button closes, `ctxf-open` class toggled |
| JS API | `open()`, `close()`, `toggle()`, `setBadge()`, `clearBadge()`, badge hides on open, `on()` events |
| Greeting & pills | Greeting appears on first open, not repeated on re-open, 3 pills visible, pills hidden after send, pill click sends message |
| Messaging & streaming | Visitor bubble, input cleared, thinking dots, input disabled during stream, agent bubble replaces dots, input re-enabled, send button active state, `on("message")` events |
| Desktop design | Panel width, back button hidden, white background |
| Mobile design (<480px) | Full-width, full-height, dark background, dark header, back button visible and functional, dark pills, FAB fades on open |
| Mobile keyboard cover | Panel open does not add `ctxf-kbd`, header visible after open, focus adds `ctxf-kbd`, blur removes it, `ctxf-kbd` gone after agent responds |
| Input font-size | ≥16px on desktop and mobile (iOS auto-zoom prevention) |
| Eager session init | Brand name from KB, KB pills from session API, session ID reused (no extra `/api/session` call), fallbacks for empty name/pills |
| Backend error handling | Session 500/abort, chat 500 both attempts, dots removed, input re-enabled, retry-and-succeed |
| appearance=bubbles — initial render | Container exists in shadow DOM, exactly 3 buttons, all visible after entrance, non-empty `data-msg`, positioned above FAB, default mode has no bubbles |
| appearance=bubbles — hide on open | FAB click hides bubbles, JS API `open()` hides bubbles |
| appearance=bubbles — re-appear after close | Bubbles re-appear when panel is closed without sending a message |
| appearance=bubbles — bubble click | Opens panel, auto-sends text, bubbles stay hidden after conversation starts |
| appearance=bubbles — session pill refresh | Updates text when session returns custom pills, refreshed pills visible, does not update if conversation already started |

### CI

GitHub Actions runs the full Playwright suite on every push or PR that touches `widget/**`. Playwright report uploaded as artifact on failure.

---

## Backend Tests

Unit and integration tests using `pytest`. No credentials required — all third-party calls are mocked.

### Run locally

```bash
cd backend
pytest tests/integration/ -v
pytest tests/unit/ -v
pytest tests/e2e/test_server.py -v   # real uvicorn, no credentials
# pytest tests/e2e/test_real_pipeline.py  # requires .env with real keys
```

### Test coverage

**Unit — `tests/unit/test_select_pills.py` (13 tests)**

Pure logic tests for `select_pills()` — pill priority algorithm (gap → service → industry → fallback), language support, duplicate prevention, and 3-pill cap.

**Unit — `tests/unit/test_archive_session.py` (5 tests)**

Session archiving: `archive_session` upserts correct fields, skips when `DATABASE_URL` unset, swallows DB errors non-fatally. `db_mark_brief_sent` updates `brief_sent = true`, skips when no DB.

**Unit — `tests/unit/test_third_party_resilience.py` (28 tests)**

| Section | Tests |
|---------|-------|
| Upstash Redis | `get_knowledge_base` returns None when both Neon and Redis fail; Neon fallback to Redis works; `get_session`/`save_session`/`check_rate_limit` propagate (documented gaps) |
| Neon (asyncpg) | Empty `DATABASE_URL` skips safely; pool creation failure returns None; schema change (missing column) returns None |
| Firecrawl | No API key → empty result; SDK raises → propagates (documented gap); missing `.data` attr → empty pages; empty markdown filtered; missing metadata → URL fallback |
| OpenRouter | `extract_json` valid/prose-wrapped/invalid; `_profile_from_partial` handles empty dict, comma-string services, contact as string, gaps as string; network error propagates (documented gap); JSONDecodeError uses partial fallback |
| crawl_site fallback | `< 100 words` triggers Firecrawl; `≥ 100 words` skips Firecrawl |

**Integration — `tests/integration/test_brief.py` (10 tests)**

Brief generation + webhook dispatch: session not found, insufficient messages, KB not found, valid briefs, webhook fired/not-fired by config, payload shape validation (all required keys, contact shape, quality score).

### CI

GitHub Actions runs integration + E2E server tests on every push or PR that touches `backend/**`. No secrets required.

```yaml
# .github/workflows/backend-tests.yml
pytest tests/integration/ -v --tb=short
pytest tests/e2e/test_server.py -v --tb=short
```

### Mock strategy

All API calls are intercepted by Playwright's `page.route()` — nothing hits the real backend:

| Helper | Intercepts | Behavior |
|--------|-----------|---------|
| `mockSession` | `POST /api/session` | Returns `{ session_id, name, pills, language }` |
| `mockChat` | `POST /api/chat/**` | Returns SSE stream with reply token |
| `mockChatHang` | `POST /api/chat/**` | Never responds — keeps thinking state visible |
| `mockChatComplete` | `POST /api/chat/**` | Returns `WAITLIST_COMPLETE` signal (iframe widget) |

---

## Backend

### Architecture

```
FRONTEND (Vercel)
  index.html + try/ + widget/ → www.getcontextus.dev

BACKEND (Render — free tier, sleeps on inactivity)
  Python + FastAPI → contextus-2d16.onrender.com
  ├── POST   /api/crawl              — Start crawl job
  ├── GET    /api/crawl/{job_id}     — Poll crawl status + result
  ├── POST   /api/crawl/demo         — Seed/refresh demo KB (no TTL)
  ├── POST   /api/crawl/{job_id}/enrich — Enrich KB with manual answers
  ├── PATCH  /api/crawl/{job_id}/pills — Override quick-reply pills with custom values
  ├── POST   /api/session            — Create chat session from KB
  ├── GET    /api/session/{id}       — Get session state
  ├── POST   /api/chat/{session_id}  — Send message, receive SSE stream
  ├── POST   /api/brief/{session_id} — Generate lead brief from session
  └── GET    /api/health             — Health check (used for wake-up ping)

STORAGE (Upstash Redis — hot cache)
  kb:{job_id}       → knowledge base — 30min TTL (no TTL for demo)
  session:{id}      → chat session — 30min TTL (extended to 24h after contact captured)
  rate:{ip}:crawl   → rate limit counter — 1hr TTL (30 crawls/hr)

STORAGE (Neon Postgres — persistent archive)
  knowledge_bases   → permanent customer KBs
  customer_configs  → KB config, allowed origins, webhook URLs
  sessions          → all non-empty sessions, archived on every turn for analysis
                      (message_count, contact_captured, brief_sent, messages JSONB)
```

### Crawler

The crawler runs in two stages with automatic fallback:

**Stage 1 — httpx (free, no credits)**
- Fetches homepage with a realistic browser User-Agent (Chrome 124)
- Extracts all same-domain links from homepage HTML
- Prioritizes pages by URL keywords: `about`, `service`, `product`, `pricing`, `contact`, `team`, `feature`, `solution` scored higher; `blog`, `news`, `post`, `article` scored lower
- Crawls top 9 links + homepage = max 10 pages concurrently (semaphore 5)
- 30s timeout for all page fetches

**Stage 2 — Firecrawl (fallback)**
- Triggers when httpx returns < 100 total words (blank SPAs, Cloudflare-protected sites)
- Uses Firecrawl API to render JavaScript and bypass anti-bot systems
- Same 10-page limit
- Requires `FIRECRAWL_API_KEY` — silently skips if not set

### Quality tiers

| Tier | Criteria | Behavior |
|------|----------|----------|
| `rich` | 2000+ words, 3+ pages | Full demo, chat enabled |
| `thin` | 500–1999 words | Summary shown with warning, chat enabled |
| `empty` | < 500 words | Manual form shown to fill in business info |

### Tech stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI (Python 3.12) |
| LLM | OpenRouter via OpenAI SDK |
| Storage | Upstash Redis (hot cache) + Neon Postgres (persistent archive) |
| Streaming | SSE (Server-Sent Events) |
| Crawler | httpx + BeautifulSoup → Firecrawl fallback |
| Observability | OpenTelemetry + Honeycomb |
| Deployment | Render (free tier) |

### Observability

Distributed tracing via OpenTelemetry with Honeycomb backend (free tier: 20M events/month). 100% sampling rate for all traces.

**Instrumented spans:**

| Span name | Description | Key attributes |
|-----------|-------------|----------------|
| `chat.request` | End-to-end chat request | `session_id`, `kb_id`, `message_count`, `response_length`, `total_duration_ms` |
| `llm.stream_chat` | OpenRouter streaming response | `model`, `input_tokens`, `output_tokens`, `duration_ms` |
| `llm.generate_profile` | Company profile extraction | `model`, `input_tokens`, `output_tokens` |
| `llm.generate_brief` | Lead brief generation | `model`, `input_tokens`, `output_tokens` |
| `crawl.httpx` | HTTP-based web crawling | `url`, `pages_found`, `total_words`, `duration_ms` |
| `crawl.firecrawl` | JS rendering fallback | `url`, `pages_found`, `duration_ms` |
| `crawl.site` | Parent crawl span | `url`, `total_pages`, `total_words`, `fallback_triggered` |

**Useful Honeycomb queries:**

```sql
-- Average latency by span
AVG(duration_ms) GROUP BY name

-- Slow chat requests (>5s)
SELECT * WHERE name = 'chat.request' AND total_duration_ms > 5000

-- LLM token usage by model
SUM(output_tokens) GROUP BY model

-- Crawl fallback rate
COUNT() GROUP BY fallback_triggered
```

### API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/crawl` | Start crawling a URL, returns `job_id` |
| `GET` | `/api/crawl/{job_id}` | Poll crawl status and results |
| `POST` | `/api/crawl/demo` | Seed the permanent demo knowledge base |
| `POST` | `/api/crawl/{job_id}/enrich` | Add manual answers to enrich a thin/empty KB |
| `PATCH` | `/api/crawl/{job_id}/pills` | Override quick-reply pills with custom values |
| `POST` | `/api/session` | Create chat session from KB |
| `GET` | `/api/session/{id}` | Get session state |
| `POST` | `/api/chat/{session_id}` | Send message, receive SSE stream |
| `POST` | `/api/brief/{session_id}` | Generate lead brief from conversation |
| `GET` | `/api/health` | Health check |

### Quick start

```bash
cd backend

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys

uvicorn app.main:app --reload
# API docs: http://localhost:8000/docs
```

### Environment variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENROUTER_API_KEY` | API key from openrouter.ai | Yes |
| `UPSTASH_REDIS_REST_URL` | Upstash Redis REST URL | Yes |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis REST token | Yes |
| `FIRECRAWL_API_KEY` | Firecrawl API key (free tier: 500 pages/mo) | No — fallback disabled if unset |
| `HONEYCOMB_API_KEY` | Honeycomb API key for observability | No — telemetry disabled if unset |
| `OTEL_SERVICE_NAME` | Service name for traces | No (default: `contextus-backend`) |
| `MODEL_PROFILE` | Model for company profile generation | No (default: `anthropic/claude-3-haiku`) |
| `MODEL_CHAT` | Model for chat responses | No (default: `anthropic/claude-sonnet-4`) |
| `MODEL_BRIEF` | Model for lead brief generation | No (default: `anthropic/claude-sonnet-4`) |
| `SITE_URL` | Site URL for OpenRouter attribution | No |
| `ALLOWED_ORIGINS` | CORS allowed origins (comma-separated) | No |
| `DATABASE_URL` | Neon Postgres connection string for persistent session archiving | No — archiving disabled if unset |

### Data models

**CompanyProfile**
```json
{
  "name": "Transfez",
  "industry": "Fintech, remittance services",
  "services": ["International money transfer", "B2B payments"],
  "location": "Jakarta, Indonesia",
  "contact": { "email": "hello@transfez.com", "phone": "+62..." },
  "summary": "Licensed remittance company...",
  "gaps": ["No pricing page found"]
}
```

**KnowledgeBase**
```json
{
  "job_id": "abc123",
  "status": "complete",
  "pages_found": 10,
  "quality_tier": "rich",
  "company_profile": { ... },
  "suggested_pills": ["What services do you offer?", ...],
  "chunks": [{ "id": "...", "source": "https://...", "text": "...", "word_count": 42 }]
}
```

**LeadBrief**
```json
{
  "who": "Potential customer description",
  "need": "What they're looking for",
  "signals": "Buying signals detected",
  "open_questions": "Unanswered questions",
  "suggested_approach": "Recommended follow-up",
  "quality_score": "high",
  "contact": { "email": "...", "phone": "...", "whatsapp": "..." }
}
```

### Updating pills manually

Override the quick-reply pills on any knowledge base without re-crawling:

```bash
# Ephemeral KB (30-min TTL — no auth required)
curl -X PATCH https://contextus-2d16.onrender.com/api/crawl/{job_id}/pills \
  -H "Content-Type: application/json" \
  -d '{"pills": ["What do you offer?", "What are your prices?", "How do I get started?"]}'

# Permanent KB (customer-seeded — X-Admin-Secret required)
curl -X PATCH https://contextus-2d16.onrender.com/api/crawl/{kb_id}/pills \
  -H "Content-Type: application/json" \
  -H "X-Admin-Secret: your-admin-secret" \
  -d '{"pills": ["What do you offer?", "What are your prices?", "How do I get started?"]}'
```

**Rules:**
- Exactly **3 pills** required — the widget always renders 3 buttons
- Each pill must be a **non-empty, non-whitespace string** — blank pills are rejected with `400`
- Changes take effect on the **next session** created from this KB
- Permanent KBs require `X-Admin-Secret`; missing or wrong secret → `401`. Unset `ADMIN_SECRET` env var → `500`
- DB errors during permanence check → `503` (retry later)

**Response:**
```json
{ "job_id": "abc123", "suggested_pills": ["...", "...", "..."] }
```

---

### Render wake-up

The backend runs on Render's free tier, which sleeps after inactivity (~30–60s to wake). Both the landing page and /try page handle this gracefully:

- **Landing page** — pings `/api/health` on load, shows "Warming up server..." placeholder in the widget area, injects the real iframe once the server responds
- **Try page** — background health ping on load; shows "⚡ Server warming up — ready in ~30s" below the URL input after 2s if no response; if user submits before server wakes, the crawl screen notes the extra wait

---

## Deployment

### Frontend (Vercel)

```bash
npx vercel --prod
```

`vercel.json` sets headers on `/widget/*` to allow iframe embedding from any origin.

### Backend (Render)

Push to `backend-development` branch. Render auto-deploys on push.

Set these environment variables in the Render dashboard:
- `OPENROUTER_API_KEY`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `FIRECRAWL_API_KEY` (optional but recommended)
- `HONEYCOMB_API_KEY` (optional, enables observability)

### Branch strategy

| Branch | Purpose |
|--------|---------|
| `main` | Frontend production (Vercel) |
| `backend-development` | Backend + all active development; merges into main for frontend deploys |

---

## Design tokens

All widget colors are hardcoded hex. No CSS variables — prevents dark mode bleed from host sites.

| Token | Value | Usage |
|---|---|---|
| Black | `#000000` | Send button, visitor bubble, logo |
| Near-black | `#111111` | Visitor bubble background |
| Body text | `#222222` | Message text |
| Border | `#e0e0e0` | Widget border, dividers |
| Input bg | `#f0f0f0` | Input wrapper |
| Muted | `#888888` | Timestamps, nudge text |
| Error bg | `#fcebeb` | Error banner |
| Boundary bg | `#faeeda` | Boundary banner |

Fonts: **DM Sans** (400, 500, 700) + **DM Mono** (400, 500) — Google Fonts.

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| 1 — Widget frontend | **Done** | Vanilla JS widget, 11 states, iframe embed |
| 2 — Backend API | **Done** | FastAPI, OpenRouter LLM, Redis, SSE, Firecrawl fallback |
| 3 — /try demo page | **Done** | Full crawl → chat → brief flow, real backend wired |
| 3.5 — Observability | **Done** | OpenTelemetry + Honeycomb distributed tracing |
| 3.6 — Widget tests + Analytics | **Done** | Playwright e2e tests, Vercel Web Analytics, GitHub Actions CI |
| 3.7 — Floating widget | **Done** | Shadow DOM FAB widget, SSE streaming, mobile dark theme, keyboard handling, 54 tests |
| 3.8 — Test hardening | **Done** | Backend unit/resilience tests (41), widget error tests (17), backend CI workflow |
| 3.9 — Bubbles appearance | **Done** | `data-appearance="bubbles"` — floating pill FAB, staggered animation, session refresh, 15 tests |
| 3.10 — Session archiving | **Done** | Write-through to Neon on every turn; `brief_sent` flagged after brief; 8 new tests |
| 4 — Lead delivery | Not started | WhatsApp/email delivery of lead briefs |
| 5 — Platform plugins | Not started | WordPress, Wix (build at traction) |

---

## Brand

- Name is always lowercase: `contextus`
- Tagline: "From Contact Us to contextus."
- Logo: Black rounded square (`rx=12` in 64×64 viewBox), white "C" at DM Sans 700
