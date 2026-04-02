# contextus

**From Contact Us to contextus.**

An embeddable AI chat widget that replaces traditional contact forms with intelligent, lead-qualifying conversations. Every chat becomes a structured lead brief — who the visitor is, what they need, their urgency signals, and a suggested follow-up.

Live: [project-b0yme.vercel.app](https://project-b0yme.vercel.app)
Backend API: [contextus-2d16.onrender.com](https://contextus-2d16.onrender.com)

---

## Status

**Phase 1 — Widget frontend: complete.**
Vanilla JS widget, 11 states, iframe embed, postMessage communication.

**Phase 2 — Backend API: complete.**
FastAPI backend with OpenRouter LLM integration, web crawler (httpx + Firecrawl fallback), Redis storage, SSE streaming. Live on Render.

**Phase 3 — /try page: complete.**
Interactive demo page — paste any URL, crawl it in real time, chat with the resulting AI assistant, and generate a lead brief. Fully wired to the real backend.

---

## Project structure

```
contextus/
├── index.html                          # Landing page (Vercel)
├── try/
│   └── index.html                      # /try demo page — real backend wired
├── widget/
│   ├── widget.html                     # Standalone iframe shell
│   ├── widget.js                       # Widget component (vanilla JS, 11-state machine)
│   ├── widget.css                      # Widget styles
│   └── embed.js                        # Tier 2 inject script (placeholder)
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
│   │       └── llm.py                  # OpenRouter LLM wrapper
│   ├── requirements.txt
│   ├── render.yaml
│   └── .env.example
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

---

## Widget

### Embedding (Tier 1 — iframe)

```html
<iframe
  src="https://project-b0yme.vercel.app/widget/widget.html?apiUrl=https://contextus-2d16.onrender.com&knowledgeBaseId=YOUR_JOB_ID&name=Your+Company&greeting=Ask+us+anything...&transparent=0&dynamicHeight=1"
  width="100%"
  height="420"
  frameborder="0"
  scrolling="no"
  style="border: none; display: block;"
></iframe>

<script>
  window.addEventListener('message', function(e) {
    if (e.data && e.data.type === 'contextus:resize') {
      var iframe = document.getElementById('your-iframe-id');
      if (iframe) {
        var scrollY = window.scrollY;
        iframe.style.height = e.data.height + 'px';
        window.scrollTo(0, scrollY);
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

## Backend

### Architecture

```
FRONTEND (Vercel)
  index.html + try/ + widget/ → project-b0yme.vercel.app

BACKEND (Render — free tier, sleeps on inactivity)
  Python + FastAPI → contextus-2d16.onrender.com
  ├── POST   /api/crawl              — Start crawl job
  ├── GET    /api/crawl/{job_id}     — Poll crawl status + result
  ├── POST   /api/crawl/demo         — Seed/refresh demo KB (no TTL)
  ├── POST   /api/crawl/{job_id}/enrich — Enrich KB with manual answers
  ├── POST   /api/session            — Create chat session from KB
  ├── GET    /api/session/{id}       — Get session state
  ├── POST   /api/chat/{session_id}  — Send message, receive SSE stream
  ├── POST   /api/brief/{session_id} — Generate lead brief from session
  └── GET    /api/health             — Health check (used for wake-up ping)

STORAGE (Upstash Redis)
  kb:{job_id}       → knowledge base — 30min TTL (no TTL for demo)
  session:{id}      → chat session — 30min TTL
  rate:{ip}:crawl   → rate limit counter — 1hr TTL (30 crawls/hr)
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
| Storage | Upstash Redis (TTL-based) |
| Streaming | SSE (Server-Sent Events) |
| Crawler | httpx + BeautifulSoup → Firecrawl fallback |
| Deployment | Render (free tier) |

### API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/crawl` | Start crawling a URL, returns `job_id` |
| `GET` | `/api/crawl/{job_id}` | Poll crawl status and results |
| `POST` | `/api/crawl/demo` | Seed the permanent demo knowledge base |
| `POST` | `/api/crawl/{job_id}/enrich` | Add manual answers to enrich a thin/empty KB |
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
| `MODEL_PROFILE` | Model for company profile generation | No (default: `anthropic/claude-3-haiku`) |
| `MODEL_CHAT` | Model for chat responses | No (default: `anthropic/claude-sonnet-4`) |
| `MODEL_BRIEF` | Model for lead brief generation | No (default: `anthropic/claude-sonnet-4`) |
| `SITE_URL` | Site URL for OpenRouter attribution | No |
| `ALLOWED_ORIGINS` | CORS allowed origins (comma-separated) | No |

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
| 4 — Lead delivery | Not started | WhatsApp/email delivery of lead briefs |
| 5 — Platform plugins | Not started | WordPress, Wix (build at traction) |

---

## Brand

- Name is always lowercase: `contextus`
- Tagline: "From Contact Us to contextus."
- Logo: Black rounded square (`rx=12` in 64×64 viewBox), white "C" at DM Sans 700
