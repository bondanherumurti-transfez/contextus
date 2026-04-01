# `/try` Page — Proof of Magic Implementation Plan

## Purpose

Give prospects a live, personalized demo using their own website.
The landing page sells the concept. `/try` makes it real.

A visitor pastes their URL → watches contextus crawl their site → chats with
an AI that already knows their business → sees the lead brief that would be
generated for every future visitor.

---

## Architecture Decision

**Single static HTML page (`/try/index.html`) with JS-managed states.**

- No routing, no framework, no build step — consistent with the rest of the frontend
- Vercel serves it as a static page
- State transitions are pure DOM manipulation, same pattern as `widget.js`
- Backend API already has everything needed: `/api/crawl`, `/api/session`, `/api/chat`, `/api/brief`

---

## Page States

```
idle → crawling → ready → chatting → brief
```

| State | Trigger | What the user sees |
|-------|---------|-------------------|
| `idle` | Page load | URL input form |
| `crawling` | Form submit | Progress messages + pages found counter |
| `ready` | `status: complete` | Company summary strip + widget with pills |
| `chatting` | First message sent | Widget active, brief hint appears after 3 messages |
| `brief` | "See lead brief" clicked | Structured brief card + CTA |

---

## State Designs

### State 1 — idle

```
contextus                                    [Get early access]

    See it work on your website.
    Paste your URL — we'll build a live demo in ~30 seconds.

    [ https://your-site.com              → ]

    No signup required · Works on any website
```

- Full-page centered layout, minimal chrome
- URL input styled consistently with landing page (`.ci-wrap` pattern)
- Validates URL on submit (http/https only, no localhost)
- "Back to home" link top-left

---

### State 2 — crawling

```
    Analyzing your website...

    [ ████████░░░░░░░░ ]

    ✓ Found homepage
    ✓ Reading 4 pages...
      Extracting services and building your profile...

    yoursite.com
```

- URL input replaced by locked URL display
- Progress messages streamed from polling `GET /api/crawl/{job_id}`
  - `crawling` → "Finding pages on your site..."
  - `analyzing` → "Reading your content..."
  - `complete` → transitions to ready state
- Pages found counter increments as `pages_found` grows
- Progress shown as animated steps, not a spinner — makes the crawl feel impressive
- If crawl fails: friendly error with retry button

---

### State 3 — ready

```
    Here's what contextus learned about Acme Agency

    [ Web Agency ]  [ Jakarta ]  [ 4 pages crawled ]

    ┌─────────────────────────────────────────────┐
    │  C  Acme Agency                             │
    │                                             │
    │  Ask us anything...                         │
    │                                             │
    │  [What's included?]  [What are your prices?]│
    │  [Do you work with startups?]               │
    └─────────────────────────────────────────────┘
```

- Company name pulled from `company_profile.name`
- Summary strip: industry tag, location (if found), pages crawled count
- Widget iframe appears using the real crawled KB:
  `src="/widget/widget.html?apiUrl=...&knowledgeBaseId={job_id}&name={company_name}&greeting=Ask+anything+about+{company_name}..."`
- Pills are crawl-generated (already implemented in Phase A)
- Subtle note: "This is how it would look on your site"

---

### State 4 — chatting

- User is in the widget, no UI change on the outer page
- After 3 messages: a soft nudge appears below the widget:
  ```
  "Based on this conversation, contextus would generate a lead brief.
   Want to see what it looks like?"  [See lead brief →]
  ```
- The "See lead brief" button calls `POST /api/brief/{session_id}`

---

### State 5 — brief

```
    This is what you'd get for every visitor.

    ┌─────────────────────────────────────────────┐
    │  New lead — [Visitor name or "Anonymous"]   │
    │  via yoursite.com · just now                │
    ├─────────────────────────────────────────────┤
    │  WHO       [extracted from conversation]    │
    │  NEED      [extracted from conversation]    │
    │  SIGNALS   [buying signals found]           │
    │  OPEN Qs   [unresolved questions]           │
    │  APPROACH  [suggested follow-up]            │
    │  QUALITY   High / Medium / Low              │
    └─────────────────────────────────────────────┘

    Every visitor who chats gets you a brief like this.

    [Add this to your site →]     [Start over]
```

- Brief card uses same visual style as the landing page `.be` component
- "Add this to your site" → scrolls to / links to early access signup
- "Start over" → resets to idle state, clears job

---

## Files to Create / Change

| File | Change |
|------|--------|
| `try/index.html` | New page — all 5 states, JS state machine, styles |
| `index.html` | Add "Try it free" CTA to nav + hero section |

No backend changes needed — all existing API endpoints are sufficient.

---

## State Machine (JS)

```js
const state = {
  phase: 'idle',       // idle | crawling | ready | chatting | brief
  jobId: null,
  sessionId: null,
  companyProfile: null,
  briefData: null,
  messageCount: 0,
  pollTimer: null,
};

function transition(phase) { ... }
```

Key functions:
- `submitUrl(url)` — validates URL, calls `POST /api/crawl`, transitions to `crawling`
- `startPolling(jobId)` — polls `GET /api/crawl/{job_id}` every 2s, updates progress messages
- `onCrawlComplete(kb)` — extracts profile, builds iframe src, transitions to `ready`
- `listenForMessages()` — listens for `contextus:messagecount` postMessage from widget iframe to track message count
- `showBriefHint()` — appears after 3 messages
- `generateBrief(sessionId)` — calls `POST /api/brief/{session_id}`, renders brief card
- `reset()` — clears all state, transitions back to `idle`

---

## Widget ↔ Page Communication

The widget lives in an iframe. The outer page needs to know when:
1. A session is created (to get `session_id` for brief generation)
2. A message is sent (to trigger the "See lead brief" hint after 3 messages)

**Session ID:** The `/try` page creates the session itself (same as `widget.html` does via `POST /api/session`) — it builds the iframe src with the job_id and stores the `session_id` before rendering the iframe. No postMessage needed for this.

**Message count:** Add a `postMessage` from `widget.js` when a message is sent:
```js
window.parent.postMessage({ type: 'contextus:message_sent', count: messageCount }, '*');
```
The `/try` page listens and increments its own counter to trigger the brief hint.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Invalid URL | Inline validation error, no API call |
| Crawl fails (`status: failed`) | Error message with retry button |
| Crawl timeout (>90s) | Timeout message with retry |
| Session creation fails | Skip to manual fallback (open widget without pre-created session) |
| Brief generation fails | Hide brief button, show generic "contact us" CTA |
| Rate limit hit (3 crawls/hr) | "Too many requests" with friendly message |

---

## Landing Page Changes

Two small additions to `index.html`:

1. **Nav:** Add "Try it free →" link next to "Get early access"
2. **Hero:** Add below the demo widget:
   ```
   Want to see it work on your own site?  [Try with your URL →]
   ```
   Links to `/try`

---

## Verification Steps

1. Open `/try` → URL input renders, submit with invalid URL → validation error shown
2. Submit valid URL → crawls, progress messages update, pages found increments
3. Crawl completes → company name shown, widget iframe appears with crawl-based pills
4. Chat 3+ messages → brief hint appears below widget
5. Click "See lead brief" → brief card renders with real data from conversation
6. Click "Start over" → resets cleanly to idle
7. Test with thin site (1 page) → still works, fallback pills shown
8. Test with rate limit → friendly error message
9. Landing page nav "Try it free" → routes to `/try`
