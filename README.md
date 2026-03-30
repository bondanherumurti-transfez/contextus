# contextus

**From Contact Us to contextus.**

An embeddable AI chat widget that replaces traditional contact forms with intelligent, lead-qualifying conversations. Every chat becomes a structured lead brief — who the visitor is, what they need, their urgency signals, and a suggested follow-up — delivered to your WhatsApp or email.

Live: [project-b0yme.vercel.app](https://project-b0yme.vercel.app)

---

## Status

**Phase 1 — Widget frontend: complete.**
The widget runs on the contextus landing page as a dogfood deployment. All 11 states are implemented against the design guideline. Responses are powered by a mock keyword engine. Real LLM integration (Phase 2) is not yet built.

---

## Project structure

```
contextus/
├── index.html                          # Landing page (live deployment)
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
│   ├── contextus-widget-design-guideline.html  # Pixel-level spec for all 11 states
│   └── prd-contextus.docx                      # Full PRD
├── CLAUDE-CODE-BRIEF.md                # Implementation brief for Claude Code
└── vercel.json                         # Vercel headers config (iframe embedding)
```

---

## Widget

### Embedding (Tier 1 — iframe)

The simplest embed. Works on any website builder (Webflow, WordPress, Wix, Squarespace, Notion, etc.).

```html
<iframe
  src="https://contextus-five.vercel.app/widget/widget.html?transparent=1&dynamicHeight=1&name=contextus&greeting=Ask%20anything%20about%20contextus..."
  width="100%"
  height="420"
  frameborder="0"
  scrolling="no"
  style="border: none; display: block; min-width: 320px;"
></iframe>
```

Add the resize listener to the parent page so the iframe grows with conversation:

```html
<script>
  window.addEventListener('message', function(e) {
    if (e.data && e.data.type === 'contextus:resize') {
      var iframe = document.getElementById('contextus-iframe');
      if (iframe) {
        var scrollY = window.scrollY;
        iframe.style.height = e.data.height + 'px';
        window.scrollTo(0, scrollY); // prevent browser autoscroll on resize
      }
    }
  });
</script>
```

### URL parameters

| Param | Values | Description |
|---|---|---|
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
| 6 | boundary | Agent hits knowledge limit. Amber banner. Redirects to team. |
| 7 | contact | Contact info captured. Lead brief starts. |
| 8 | idle-nudge | 60s silence. Single muted italic nudge. |
| 9 | error | Network/LLM timeout. Red banner. Auto-retries once after 2s. |
| 10 | returning | Previous conversation shown at 55% opacity with label. |
| 11 | complete | Sign-off message. "Conversation ended — lead brief sent." Soft-reset after 30s. |

### Dynamic height behavior

When `dynamicHeight=1`:
- `widget.js` observes the widget element with `ResizeObserver`
- On any size change, sends `postMessage({ type: 'contextus:resize', height })` to the parent
- Parent updates `iframe.style.height` and restores `window.scrollY` to prevent page autoscroll
- `max-height` on the message area is disabled in JS so the widget expands freely and never triggers internal scroll for short conversations

When `dynamicHeight=0`:
- `max-height: 400px` (desktop) / `50vh` (mobile) applies on the message area
- Content overflows internally with a scrollbar — correct for fixed-height embeds

---

## Design tokens

All colors are hardcoded hex. No CSS variables. This prevents dark mode bleed from host sites.

| Token | Value | Usage |
|---|---|---|
| Black | `#000000` | Send button active, visitor bubble, logo |
| Near-black | `#111111` | Visitor bubble background |
| Body text | `#222222` | Message text |
| Border | `#e0e0e0` | Widget border, dividers |
| Input bg | `#f0f0f0` | Input wrapper background |
| Muted | `#888888` | Timestamps, nudge text |
| Error bg | `#fcebeb` | Error banner |
| Boundary bg | `#faeeda` | Boundary banner |

Fonts: **DM Sans** (400, 500, 700) + **DM Mono** (400, 500) — loaded from Google Fonts.

---

## Deployment

Uses [Vercel](https://vercel.com). No build step.

```bash
# Deploy to production
npx vercel --prod
```

`vercel.json` sets headers on `/widget/*` to allow iframe embedding from any origin:

```json
{
  "headers": [
    {
      "source": "/widget/(.*)",
      "headers": [
        { "key": "X-Frame-Options", "value": "ALLOWALL" },
        { "key": "Content-Security-Policy", "value": "frame-ancestors *" }
      ]
    }
  ]
}
```

> **Note:** `git push` deploys are blocked on Vercel Hobby plan due to author checks. Use `npx vercel --prod` from the CLI instead.

---

## Bugs fixed (Phase 1)

**CSS reset specificity conflict** — `#contextus-widget * { padding: 0; margin: 0 }` (specificity 1,0,0) overrode all class-level padding and margin rules (specificity 0,1,0). Fixed by removing `padding: 0` and `margin: 0` from the reset — it now only sets `box-sizing: border-box`.

**Bottom border clipped** — `scrollHeight` excludes borders, so the iframe was 1px too short. Fixed with `Math.ceil(widget.getBoundingClientRect().height)` which includes sub-pixel borders.

**Greeting on idle** — Design spec says State 1 (idle) shows only header + input + pills. Greeting was incorrectly shown on load. Fixed by moving greeting injection to first `sendMessage()` call.

**Mobile scroll after agent response** — Two compounding bugs:
1. Parent page resize handler didn't preserve `window.scrollY`. When the iframe grew taller on agent response, the browser autoscrolled the page to keep the iframe bottom visible, pushing the top of the widget (greeting + visitor bubble) off screen.
2. `renderBanners()` unconditionally set `msgArea.scrollTop = msgArea.scrollHeight` on every render, unlike `renderMessages()` which had a guard.
3. At viewport widths < 480px, the CSS `max-height: 50vh` on the message area capped it smaller than the content, creating artificial overflow that triggered the scroll-to-bottom condition.

Fixed by: saving/restoring `scrollY` in the resize listener, guarding `scrollTop` in `renderBanners()`, and disabling `max-height` on the message area when `dynamicHeight=1`.

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| 1 — Widget frontend | **Done** | Vanilla JS widget, 11 states, iframe embed, mock responses |
| 2 — Backend API | Not started | FastAPI (Python), WebSocket streaming, Claude API, pgvector RAG |
| 3 — Lead brief engine | Not started | Conversation summarization, WhatsApp/email delivery |
| 4 — Landing page (real LLM) | Not started | Swap mock engine for real backend |
| 5 — Platform plugins | Not started | WordPress, Wix (build at traction, not before) |

---

## Brand

- Name is always lowercase: `contextus`
- Tagline: "From Contact Us to contextus."
- Logo: Black rounded square (`rx=12` in 64×64 viewBox), white "C" at DM Sans 700
