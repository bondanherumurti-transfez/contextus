# contextus — Implementation Brief for Claude Code

> **From Contact Us to contextus.**
> An inline AI chat widget that replaces traditional contact forms with intelligent, lead-qualifying conversations.

---

## Project context

contextus is an embeddable chat widget that sits on a business's website where a "Contact Us" form would normally go. Visitors chat with an AI agent grounded in the business's knowledge base. Every conversation is automatically summarized into a structured lead brief (who they are, what they need, qualification signals, suggested follow-up approach) and delivered to the business owner via WhatsApp or email.

**Current stage:** Pre-launch MVP. The first deployment target is the contextus landing page itself (dogfooding). The widget on the landing page answers questions about contextus. Second deployment will be a tax/accounting firm's website.

**What exists already:**
- Product Requirements Document (PRD v1.2) — full product spec
- Landing page (HTML) — live, needs widget integration
- Widget design guideline (HTML) — pixel-level spec for all 11 widget states
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

### Phase 1: Widget frontend
**Goal:** A standalone, embeddable inline chat component that matches the design guideline exactly.

**Read:** `docs/contextus-widget-design-guideline.html` — it has every color hex, font spec, border radius, button state, and widget state mockup.

**Key specs:**
- Monochrome only. All colors hardcoded (no CSS variables). Prevents dark mode bleed on host sites.
- Font: DM Sans (400, 500, 700) + DM Mono (400). Load from Google Fonts.
- Input wrapper: `#f0f0f0` background, `16px` border-radius, `15px` font.
- Logo mark: Black rounded square, white "C" at DM Sans 700. Used in header (18px), agent avatar (24px), and nav.
- **Send button has 3 states:**
  - EMPTY: `bg #e0e0e0, fill #999, cursor default` — input is empty
  - ACTIVE: `bg #000, fill #fff, cursor pointer` — input has text
  - DISABLED: `bg #e0e0e0, fill #bbb, cursor not-allowed` — agent is responding, input also disabled

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

**For MVP/demo:** Wire to a mock response engine (keyword matching, like the landing page currently does). Real LLM integration comes in Phase 2.

---

### Phase 2: Backend API
**Goal:** API server that handles chat sessions, LLM orchestration, and knowledge retrieval.

**Read:** PRD Sections 5 (Functional Requirements) and 7 (Technical Architecture).

**Endpoints:**

```
POST   /api/session          — Create new chat session (returns session_id)
WS     /api/chat/:session_id — WebSocket for streaming messages
POST   /api/message           — Fallback REST endpoint if WS unavailable (SSE response)
GET    /api/session/:id       — Get session state (for returning visitors)
POST   /api/knowledge/crawl   — Trigger website crawl for tenant
PUT    /api/knowledge/:tenant — Update knowledge base
GET    /api/health            — Health check
```

**Data flow per message:**
1. Visitor message received via WebSocket
2. Tier 1 security checks (rate limit per IP, behavioral fingerprint score, pattern detection)
3. RAG retrieval: embed visitor message → vector similarity search against tenant knowledge base
4. LLM call with: system prompt (business profile + guardrails) + retrieved context + conversation history + visitor message
5. Stream response tokens back via WebSocket
6. Persist message pair to PostgreSQL with extracted metadata tags
7. On conversation end: trigger lead brief generation (Phase 3)

**Key constraints:**
- `tenant_id` on every table, even though MVP is single-tenant
- Session state in memory (no localStorage on client)
- Session expires after 30 minutes of inactivity or tab close
- Rate limit: max 5 sessions per IP per hour, max 30 messages per session

---

### Phase 3: Lead brief engine
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

---

### Phase 4: Landing page integration
**Goal:** Replace the demo keyword-matching chat on the landing page with the real widget.

**Read:** `site/index.html`

**Steps:**
1. Remove the inline demo chat JS from the landing page
2. Replace with the iframe embed pointing at the real backend:
   ```html
   <iframe src="https://contextus.ai/embed/contextus-demo?transparent=1&dynamicHeight=1"
     width="100%" height="400" frameborder="0" style="border:none;"></iframe>
   ```
3. Create a "contextus-about" knowledge base with: what contextus is, how it works, pricing direction, Bahasa support, comparison to competitors, embed instructions
4. The landing page itself becomes the first live deployment — visitors experience the product by asking about the product
5. Once validated, swap iframe for inline embed (Tier 2) for the smoother experience

---

### Phase 5: Platform plugins (NOT MVP — build at traction)
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

**Key insight:** Webflow, Squarespace, and Framer don't need plugins — they support raw HTML/iframe embedding out of the box. For these, a well-written "How to add contextus to your [platform] site" guide with screenshots is sufficient. Only WordPress, Wix, and Shopify need actual native plugins to reduce friction meaningfully.

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
# Start with Phase 1 — build the widget frontend
# Read the design guideline first, then implement

cat docs/contextus-widget-design-guideline.html
# Then build widget.js following the 11 states spec
```

---

*Generated from contextus idea refinement session, March 2026.*
