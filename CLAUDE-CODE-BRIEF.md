# contextus — Implementation Brief for Claude Code

> **From Contact Us to contextus.**
> An inline AI chat widget that replaces traditional contact forms with intelligent, lead-qualifying conversations.

---

## Project context

contextus is an embeddable chat widget that sits on a business's website where a "Contact Us" form would normally go. Visitors chat with an AI agent grounded in the business's knowledge base. Every conversation is automatically summarized into a structured lead brief (who they are, what they need, qualification signals, suggested follow-up approach) and delivered to the business owner via WhatsApp or email.

**Current stage:** Pre-launch MVP. Building the "proof of magic" — not a full product yet.

**MVP definition (critical — read this):**

The MVP is NOT a self-service platform. It's a single-page demo that hooks potential customers by showing them their own business served by an AI agent — live, in front of them, with their actual website content. The flow:

1. Visitor lands on the contextus landing page
2. Reads the value prop, sees the before/after comparison
3. Sees: **"See contextus on your website — paste your URL"**
4. Pastes their URL → system crawls in real-time (showing progress)
5. Live preview appears: a contextus widget powered by *their* content
6. They chat with it, see it answer questions about *their* business
7. Below: a sample lead brief generated from the demo conversation
8. CTA: "Want this on your website? Enter your email."

This validates the core hypothesis (does the crawl → agent → brief pipeline actually work?) with zero commitment from the customer. If they don't paste a URL — not a real prospect. If the agent gives bad answers — the crawl/RAG needs work before anything else gets built. If it works — they'll beg for it.

**What exists already:**
- Product Requirements Document (PRD v1.2) — full product spec
- Landing page (HTML) — live, needs restructuring for URL-input flow
- Widget design guideline (HTML) — pixel-level spec for all 11 widget states, animations, mobile behavior
- Logo SVGs — finalized brand mark

---

## Reference files

Read these files **on demand** when working on the relevant phase. Don't load all at once.

| File | What it contains | Read when |
|------|-----------------|-----------|
| `docs/prd-contextus.docx` | Full PRD: user journeys, functional requirements, security tiers, technical architecture, pricing strategy | Architecture decisions, feature questions |
| `docs/contextus-widget-design-guideline.html` | Widget design spec: brand tokens, anatomy, send button states, all 11 widget states with mockups and behavior rules, sizing, embed API | Building the widget frontend |
| `site/index.html` | Landing page (contextus-landing-v2.html) | Integrating widget into the landing page |
| `assets/contextus-logo-dark.svg` | Primary logo mark (black bg, white C, 700 weight) | Any UI that needs the logo |
| `assets/contextus-logo-light.svg` | Inverted logo mark (white bg, black C) | Dark background contexts |
| `assets/contextus-logo-lockup.svg` | Horizontal lockup: mark + wordmark | Headers, social |

---

## Tech stack (MVP)

| Layer | Choice | Notes |
|-------|--------|-------|
| Widget frontend | Vanilla JS + CSS (no framework) | Built as a standalone page AND an injectable script. See Embedding Strategy below. |
| Backend API | Python (FastAPI) or Node.js (Express/Hono) | WebSocket for streaming responses. REST for knowledge base management. |
| LLM | Anthropic Claude API (Sonnet) | Classification layer can use Haiku for cost optimization. |
| Knowledge base | pgvector (PostgreSQL) or Qdrant | Embedding-based semantic search over chunked business content. |
| Database | PostgreSQL | Conversations, leads, tenant config. Use `tenant_id` in all models even for single-tenant MVP. |
| Notification | WhatsApp API (simple) + email (Resend/SendGrid) | Lead brief delivery. |
| Hosting | Single VPS (DigitalOcean/Render) | Keep it simple. CDN for widget JS and embed page. |

### Embedding strategy (critical — read this first)

The widget must be embeddable by non-technical business owners who can barely paste a URL. Research on how Typeform, Tally.so, Calendly, Crisp, and HubSpot handle embedding reveals a universal pattern: **multiple tiers from easiest to most powerful.**

**Tier 1: iframe URL (MVP — build this first, dogfood with this)**

The simplest possible embed. Works on every website builder (Wix, WordPress, Squarespace, Webflow, Notion, Google Sites). The business owner pastes a URL — that's it.

```html
<iframe
  src="https://contextus.ai/embed/SITE_ID?transparent=1&dynamicHeight=1"
  width="100%" height="400" frameborder="0"
  style="border: none; min-width: 320px;">
</iframe>
```

The server renders the full widget as a standalone HTML page at `/embed/:site_id`. Key params:
- `transparent=1` — transparent background so it blends with the host page
- `dynamicHeight=1` — uses `postMessage` to tell the parent iframe to resize (like Tally does)
- `lang=auto|en|id` — language override
- `greeting=...` — custom placeholder text

This is how Tally, Calendly, and Crisp all work at their most basic level. It's the path 80% of your early customers will use.

**Tier 2: div + script (beautiful inline — build second)**

For customers who can paste HTML. The script finds a target container and injects the widget inline, with full dynamic height and event callbacks. This is the Typeform/Calendly primary pattern.

```html
<div data-contextus="SITE_ID"></div>
<script src="https://cdn.contextus.ai/embed.js" async></script>
```

The script scans for `[data-contextus]` elements, creates the widget inside them, manages height, and communicates via `postMessage`. The widget feels native — no iframe border, no scroll issues.

**Tier 3: Platform plugins (build at scale — NOT in MVP)**

Native integrations for website builders. Only build these when demand from paying customers justifies the maintenance burden.

- WordPress plugin (highest priority — largest market)
- Wix app
- Shopify app (for e-commerce contact/support)
- Webflow embed component
- Squarespace code injection guide

Each plugin is essentially a wrapper around Tier 1 or Tier 2 that simplifies installation to "click install, paste your site ID."

**Architecture implication:** The widget is a single component that renders identically whether it's loaded as a standalone page (Tier 1 iframe) or injected into a host page (Tier 2 script). Build it once as a self-contained HTML/JS/CSS bundle. The iframe URL serves it as a full page. The embed script injects it into a shadow DOM or container div.

---

## Build phases

### Phase 1: The crawl + knowledge pipeline (build first — this is the core)
**Goal:** Given a URL, crawl the site, extract content, assess quality, and produce a usable knowledge base.

**Why first:** This is the hardest unsolved problem and the foundation of everything. If the crawl produces garbage, nothing else matters — not the widget, not the embed, not the admin panel. Prove this works before building anything around it.

**Build:**

```
POST /api/crawl
  Input:  { "url": "https://example.com" }
  Output: { "job_id": "...", "status": "crawling" }

GET  /api/crawl/:job_id
  Output: {
    "status": "complete",
    "pages_found": 5,
    "quality_tier": "rich|thin|empty",
    "company_profile": { ... },
    "knowledge_chunks": [ ... ],
    "gaps": ["pricing", "team", "faq"]
  }

POST /api/crawl/:job_id/enrich
  Input:  { "answers": { "services": "...", "pricing": "...", "guardrails": "..." } }
  Output: { "company_profile": { ...updated }, "knowledge_chunks": [ ...updated ] }
```

**Crawler implementation:**
1. Fetch the URL + discover linked pages (same domain, max 20 pages, max 30s total)
2. Extract text content (strip nav, footer, boilerplate — keep headings, paragraphs, lists)
3. Chunk content into ~500 token segments with overlap
4. Generate embeddings (Anthropic or OpenAI embeddings API)
5. Store in vector DB (pgvector) with metadata (source URL, page title, chunk index)
6. Generate a structured Company Profile via single LLM call:
   ```json
   {
     "name": "extracted or inferred",
     "industry": "extracted or inferred",
     "services": ["list of services found"],
     "location": "if found",
     "contact": "if found",
     "summary": "2-3 sentence description",
     "gaps": ["what's missing — pricing? team? FAQ?"]
   }
   ```
7. Assess quality tier based on content volume:
   - **rich**: 10+ meaningful paragraphs across 3+ pages → proceed to demo
   - **thin**: some content but significant gaps → show profile + guided interview
   - **empty**: almost nothing extracted → skip to guided interview

**Crawl quality tiers — how each is handled:**

```
RICH (≈30% of SMB sites):
  Site has real content. Services pages, about us, maybe pricing.
  → Show: "Here's what contextus knows about your business:" + company profile
  → Then: Live widget demo immediately
  → Optional: "Want to add more detail?" link to guided interview

THIN (≈50% of SMB sites):
  Some content but gaps. Maybe just homepage + one services page.
  → Show: "We found [N] pages. Here's what contextus knows so far:" + partial profile
  → Then: "Help contextus learn more — answer 3 quick questions:" + inline interview
  → Then: Live widget demo with enriched knowledge base

EMPTY (≈20% of SMB sites):
  Almost nothing — logo, hero image, WhatsApp button.
  → Show: "Your website is clean and minimal — let's teach contextus directly."
  → Then: Guided interview (5 questions) — framed as normal, not as failure
  → Then: Live widget demo with interview-based knowledge base
```

**Guided interview questions (asked inline on the landing page):**
1. "What are your main services?" (free text, 1-2 sentences)
2. "What do customers usually ask about?" (free text)
3. "What's your typical price range?" (free text, optional)
4. "What should contextus NOT answer? (e.g., specific pricing, legal advice)" (free text)
5. "What's the best way for customers to reach your team?" (WhatsApp/email/phone)

Each answer gets chunked, embedded, and added to the knowledge base. The Company Profile updates in real-time.

**Deliverable:** An API that takes a URL, produces a knowledge base and company profile, honestly reports quality, and accepts enrichment from guided interview answers. Ephemeral by default — demo knowledge bases expire after 30 minutes.

---

### Phase 2: Widget frontend
**Goal:** A standalone, embeddable inline chat component that matches the design guideline exactly.

**Read:** `docs/contextus-widget-design-guideline.html` — it has every color hex, font spec, border radius, button state, widget state mockup, animation spec, and mobile behavior rules.

**Key specs:**
- Monochrome only. All colors hardcoded (no CSS variables). Prevents dark mode bleed on host sites.
- Font: DM Sans (400, 500, 700) + DM Mono (400). Load from Google Fonts.
- Input wrapper: `#f0f0f0` background, `16px` border-radius, `15px` font.
- Logo mark: Black rounded square, white "C" at DM Sans 700. Used in header (18px), agent avatar (24px).
- **Send button has 3 states:**
  - EMPTY: `bg #e0e0e0, fill #999, cursor default` — input is empty
  - ACTIVE: `bg #000, fill #fff, cursor pointer` — input has text
  - DISABLED: `bg #e0e0e0, fill #bbb, cursor not-allowed` — agent is responding, input also disabled
- **Animations:** See design guideline Section 05. Messages fade in + slide up (200-300ms). Container height transitions smoothly. Send button transitions 120ms between empty/active, snaps instantly to disabled.
- **Mobile:** See design guideline Section 06. 16px input font (prevents iOS zoom), 50vh scroll max-height, 36px send button touch target, horizontal-scrolling pills.

**11 widget states to implement:**

```
1. idle          — Input + pills. Send button EMPTY.
2. visitor-typing — Text in input. Send button ACTIVE.
3. agent-thinking — Message sent. Typing dots. Input disabled. Send DISABLED.
4. active        — Multi-turn. Send button EMPTY, ready for text.
5. scroll        — Messages exceed max-height (400px desktop, 50vh mobile). Input pinned.
6. boundary      — Agent can't answer. Graceful redirect to human. Amber banner.
7. contact       — Contact info captured. Agent confirms. System starts lead brief.
8. idle-nudge    — 60s silence. One muted italic nudge. Max one per conversation.
9. error         — LLM timeout/network fail. Red inline error. Auto-retry once after 2s.
10. returning    — Previous conversation at 55% opacity. "Previous conversation" label.
11. complete     — Sign-off. "Conversation ended — lead brief sent." Soft-reset after 30s.
```

**Deliverable:** A single widget component that works in two modes:

1. **Standalone page** at `/embed/:site_id` — serves the full widget as an HTML page (for iframe embedding)
2. **Inject script** at `/embed.js` — finds `[data-contextus]` elements and injects the widget inline

Both share the same widget code. The standalone page just wraps it in a minimal HTML shell with `transparent=1` support.

```html
<!-- Tier 1: iframe (MVP — test with this) -->
<iframe src="https://contextus.ai/embed/demo?transparent=1&dynamicHeight=1"
  width="100%" height="400" frameborder="0" style="border:none;"></iframe>

<!-- Tier 2: inline (build second) -->
<div data-contextus="demo"></div>
<script src="https://cdn.contextus.ai/embed.js" async></script>
```

**The widget must accept a knowledge base ID** (or ephemeral session ID for demos) so it can connect to the right backend context. For the MVP demo, this is a temporary ID generated by the crawl pipeline.

---

### Phase 3: Chat backend + RAG
**Goal:** API server that handles chat sessions, LLM orchestration, and knowledge retrieval.

**Read:** PRD Sections 5 (Functional Requirements) and 7 (Technical Architecture).

**Endpoints:**

```
POST   /api/session          — Create new chat session (returns session_id, accepts knowledge_base_id)
WS     /api/chat/:session_id — WebSocket for streaming messages
POST   /api/message           — Fallback REST endpoint if WS unavailable (SSE response)
GET    /api/session/:id       — Get session state (for returning visitors)
GET    /api/health            — Health check
```

**Data flow per message:**
1. Visitor message received via WebSocket
2. Tier 1 security checks (rate limit per IP, behavioral fingerprint score, pattern detection)
3. RAG retrieval: embed visitor message → vector similarity search against tenant knowledge base
4. LLM call with: system prompt (company profile + guardrails) + retrieved context + conversation history + visitor message
5. Stream response tokens back via WebSocket
6. Persist message pair to PostgreSQL with extracted metadata tags
7. On conversation end: trigger lead brief generation (Phase 4)

**Key constraints:**
- `tenant_id` on every table, even though MVP is single-tenant
- Session state in memory (no localStorage on client)
- Session expires after 30 minutes of inactivity or tab close
- Rate limit: max 5 sessions per IP per hour, max 30 messages per session

---

### Phase 4: Lead brief engine
**Goal:** Summarize conversations into structured lead briefs and deliver them.

**Read:** PRD Section 3.3 (Lead Brief Generation) and the Alamii Food example in the landing page.

**Lead brief structure:**
```json
{
  "tenant_id": "string",
  "session_id": "string",
  "created_at": "datetime",
  "who": "Extracted visitor identity — name, company, role, size, industry",
  "need": "What services/solutions they asked about",
  "signals": "Qualification signals — urgency, budget, buying intent vs browsing",
  "open_questions": "Questions agent redirected to humans (follow-up hooks)",
  "suggested_approach": "AI-generated follow-up recommendation",
  "quality_score": "high | medium | low — based on coherence, specificity, contact provided",
  "contact": { "type": "whatsapp|email|phone", "value": "string" },
  "conversation_transcript": "Full message array",
  "metadata": { "duration_seconds": 0, "message_count": 0, "language": "en|id" }
}
```

**Generation pipeline:**
1. Conversation ends (visitor signals completion, or 5 min idle after contact captured)
2. Single LLM call (Sonnet) with structured prompt: "Given this conversation, extract the following fields..."
3. Quality scoring: coherence check, contact info presence, message count, response patterns
4. Store lead record in PostgreSQL
5. Deliver via configured channel (WhatsApp message or email) to business owner

**For MVP demo:** Generate a sample lead brief from the demo conversation and display it on the landing page below the widget. This shows the potential customer what their sales team would receive. No delivery yet — just the visual output.

---

### Phase 5: Landing page — the "proof of magic"
**Goal:** Restructure the landing page so the primary CTA is "paste your URL" instead of "join waitlist."

**Read:** `site/index.html`

**The landing page becomes three acts:**

**Act 1 — The pitch (above the fold):**
- Hero: "From Contact Us to contextus."
- Subtitle + before/after comparison (already exists)
- The contextus widget about contextus (dogfooding — already exists as demo)

**Act 2 — The proof (mid-page, primary CTA):**
- Heading: "See contextus on your website"
- Subtext: "Paste your URL. In 60 seconds, you'll see your business served by an AI agent."
- URL input field (same monochrome style as the chat input — `#f0f0f0` background, 16px radius)
- On submit:
  - Show crawl progress: "Reading your homepage... Found 4 pages... Building knowledge base..."
  - Assess quality → branch to rich/thin/empty flow
  - If thin/empty: show guided interview inline
  - Show live widget preview with their content
  - Show sample lead brief from a demo conversation
  - CTA below: "Want this on your website? Enter your email."

**Act 3 — The details (below the fold):**
- How it works (3 steps — already exists)
- Implementation section (already exists)
- Lead brief example (Alamii Food — already exists)
- Final email capture CTA

**Key technical decisions for the demo:**
- Demo knowledge bases are ephemeral — stored with a TTL of 30 minutes, then purged
- Rate limit: max 3 URL crawls per IP per hour (prevent abuse)
- The demo widget uses the same component as the real widget — it's not a mock
- No account creation. No login. No sign-up before trying.

---

### Phase 6: Customer onboarding (build only after Phase 5 converts)
**Goal:** The people who tried the demo and said "I want this" get onboarded.

**Only build this when you have 10+ email signups from the demo who explicitly asked for it.**

**Flow:**
1. Customer receives email: "Your contextus agent is ready to set up"
2. Link takes them to onboarding page (simple, no account yet)
3. Shows the Company Profile generated during their demo (it was saved when they signed up)
4. "Review and edit" — they can fix anything the crawl got wrong
5. Define guardrails: "What should contextus NOT answer?"
6. Choose notification channel: WhatsApp or email for lead briefs
7. Get embed code: iframe URL (Tier 1) — copy and paste
8. Done. Widget is live on their site.

**Admin panel (minimal):**
- List of lead briefs received
- Conversation transcripts (expandable)
- Knowledge base editor (edit Company Profile, add/remove content)
- Embed code reference

---

### Phase 7: Platform plugins (NOT MVP — build at traction)
**Goal:** Native integrations for popular website builders. Only pursue when paying customers request them.

**Priority order (by market size and customer demand):**

| Platform | Implementation | Effort |
|----------|---------------|--------|
| WordPress | Plugin that adds a shortcode `[contextus id="SITE_ID"]` or Gutenberg block. Wraps Tier 1 iframe internally. | Medium |
| Wix | Wix App that uses an HTML embed component. Published to Wix App Market. | Medium |
| Webflow | Custom embed component + documentation page. Webflow supports raw HTML natively. | Low (docs only) |
| Shopify | Shopify App that injects the script via theme extension. For e-commerce support/contact. | Medium-High |
| Squarespace | Code injection guide (Squarespace supports `<script>` in page headers). | Low (docs only) |
| Framer | Embed component guide. Framer supports iframes natively. | Low (docs only) |

**Don't build any of this until:**
- You have 10+ paying customers asking for a specific platform
- The iframe embed (Tier 1) is causing real friction for that platform's users
- You have the bandwidth to maintain the plugin (every platform update can break plugins)

---

## Critical constraints (always apply)

**Brand:**
- Name is always lowercase: `contextus` — never "Contextus"
- Tagline: "From Contact Us to contextus."
- Font: DM Sans (body) + DM Mono (labels/code)
- Logo: Black rounded square (rx=12 in 64 viewBox), white C at weight 700

**Security (even in MVP):**
- Rate limiting per IP (5 sessions/hr, 30 messages/session)
- Prompt injection defense: strong system prompt boundaries, never leak system prompt or raw knowledge base
- The agent MUST refuse rather than hallucinate when it doesn't know something
- Every lead brief includes a quality score (doubles as bot/spam verification)

**Dark mode defense:**
- All widget colors are hardcoded hex — no CSS variables
- Widget sets `color-scheme: light` on its container
- The landing page uses `<meta name="color-scheme" content="light only">`

**Session management:**
- State in memory only — no localStorage, no cookies
- Session = tab lifespan or 30 minutes, whichever is shorter
- No cross-visit tracking

**Agent behavior rules:**
- Never answer beyond the knowledge boundary — graceful redirect instead
- Never ask more than one question per turn
- Qualification data is extracted silently, not through robotic question sequences
- The refusal-to-answer moment IS the lead capture mechanism

---

## Suggested starting command

```bash
# Start with Phase 1 — the crawl + knowledge pipeline
# This is the core of the product. Everything else is a wrapper.

# Build the crawler:
#   Input: a URL
#   Output: company profile + knowledge chunks + quality tier
#
# Test it against 10 real Indonesian SMB websites before moving to Phase 2.
# If the crawl produces useful content for 7/10 sites, proceed.
# If not, improve the crawler before building anything else.
```

---

*Generated from contextus idea refinement session, March 2026.*
