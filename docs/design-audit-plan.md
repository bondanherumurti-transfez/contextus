# contextus Widget — Design Audit Plan

**Version:** 1.0 · March 2026
**Scope:** Iframe embed (Tier 1 MVP). Run this audit before any new deployment and when testing on a new host platform.

---

## How to use this

Work through each section in order. For each check, mark it:
- ✅ Pass
- ❌ Fail — note what's wrong
- ⚠️ Partial — note the condition

When auditing on a new platform, complete the full audit. For routine deploys, run Section 1 (tokens), Section 4 (states), and Section 6 (platform).

---

## Tools needed

| Tool | Purpose |
|---|---|
| Browser DevTools (Chrome or Safari) | Inspect computed styles, responsive emulation |
| DevTools device toolbar | Simulate mobile (375px iPhone SE, 390px iPhone 15) |
| DevTools color picker | Verify exact hex values on rendered pixels |
| Screenshot comparison | Place audit screenshot next to design guideline mockup |
| Desktop viewport 1280px | Baseline desktop audit |
| Viewport 544px | Wide-narrow boundary (above 480px breakpoint) |
| Viewport 375px | Mobile (below 480px breakpoint) |

---

## Section 1 — Brand tokens

Verify computed styles in DevTools against the spec. Check on `#contextus-widget` and its children.

### Colors

| Token | Spec | Element to check | Pass/Fail |
|---|---|---|---|
| Background | `#ffffff` | `#contextus-widget`, `.ctx-messages`, `.ctx-input-area` | |
| Body text | `#222222` | `.ctx-bubble-agent` | |
| Visitor bubble bg | `#111111` | `.ctx-bubble-visitor` | |
| Visitor bubble text | `#ffffff` | `.ctx-bubble-visitor` | |
| Border | `#e0e0e0` | `#contextus-widget` border, `.ctx-header` border-bottom | |
| Input wrapper bg | `#f0f0f0` | `.ctx-input-wrapper` | |
| Placeholder text | `#bbbbbb` | `input::placeholder` | |
| Send btn EMPTY bg | `#e0e0e0` | `.ctx-send-empty` | |
| Send btn EMPTY icon | `#999999` | `.ctx-send-empty svg` fill | |
| Send btn ACTIVE bg | `#000000` | `.ctx-send-active` | |
| Send btn ACTIVE icon | `#ffffff` | `.ctx-send-active svg` fill | |
| Send btn DISABLED bg | `#e0e0e0` | `.ctx-send-disabled` | |
| Send btn DISABLED icon | `#bbbbbb` | `.ctx-send-disabled svg` fill | |
| Error banner bg | `#fcebeb` | `.ctx-banner-error` | |
| Error banner text | `#a32d2d` | `.ctx-banner-error` color | |
| Boundary banner bg | `#faeeda` | `.ctx-banner-boundary` | |
| Boundary banner text | `#854f0b` | `.ctx-banner-boundary` color | |
| Complete banner bg | `#fafafa` | `.ctx-banner-complete` | |
| Complete accent text | `#0f6e56` | `.ctx-banner-complete span` | |
| Muted/nudge text | `#888888` | `.ctx-nudge`, `.ctx-header-powered` | |

> **Dark mode check:** Open DevTools → Rendering → Force dark mode. Every color above should remain identical — no inversion. `color-scheme: light` on `#contextus-widget` must hold.

### Typography

| Element | Font | Weight | Size | Pass/Fail |
|---|---|---|---|---|
| Input text | DM Sans | 400 | 15px (16px mobile) | |
| Agent message | DM Sans | 400 | 13px | |
| Visitor bubble | DM Sans | 400 | 13px | |
| Header name | DM Sans | 500 | 13px | |
| Pill buttons | DM Sans | 400 | 11px | |
| "powered by contextus" | DM Mono | 400 | 10px | |

> **Font loading check:** Throttle network to "Slow 3G", reload. Confirm DM Sans and DM Mono load correctly. Check that fallback (`-apple-system`, `sans-serif`) doesn't cause layout shift that breaks the widget chrome.

### Spacing & border radii

| Element | Spec | Pass/Fail |
|---|---|---|
| Widget border | 0.5px solid `#e0e0e0` | |
| Widget border-radius | 12px | |
| Header padding | 10px 14px | |
| Message area padding | 14px | |
| Input area padding | 0 14px 14px | |
| Input wrapper border-radius | 16px | |
| Send button size | 34×34px | |
| Send button border-radius | 8px | |
| Visitor bubble border-radius | 12px (bottom-right: 3px) | |
| Pill border-radius | 14px | |
| Error/boundary banner border-radius | 8px | |
| Avatar size (header logo) | 18×18px | |
| Avatar size (message) | 24×24px | |

---

## Section 2 — Send button states

Test each transition in sequence.

| Step | Action | Expected send button state | Pass/Fail |
|---|---|---|---|
| 1 | Page loads, input empty | EMPTY — bg `#e0e0e0`, icon `#999`, cursor `default` | |
| 2 | Type any character | ACTIVE — bg `#000`, icon `#fff`, cursor `pointer` | |
| 3 | Clear the input | EMPTY — back to gray | |
| 4 | Type a message, press Enter | DISABLED — bg `#e0e0e0`, icon `#bbb`, cursor `not-allowed` | |
| 5 | While disabled, try clicking send | Nothing happens (no double-send) | |
| 6 | Agent responds | EMPTY — re-enables, input clears | |
| 7 | Click a pill | Immediately DISABLED while agent responds | |

---

## Section 3 — Widget anatomy

### Header

| Check | Pass/Fail |
|---|---|
| Logo mark renders at 18×18px — black rounded square, white C | |
| Header name shows correct custom name | |
| "powered by contextus" right-aligned, DM Mono 10px, `#bbbbbb` | |
| 0.5px bottom border separates header from message area | |
| Header does not scroll with messages (stays pinned) | |

### Message area

| Check | Pass/Fail |
|---|---|
| Agent messages: 24×24px avatar left, text right of avatar | |
| Visitor messages: right-aligned, no avatar | |
| 8px gap between avatar and bubble | |
| 10px margin-bottom between message rows | |
| Agent bubble text is plain (no background, no padding box) | |
| Visitor bubble text is white on `#111111`, 8px 13px padding, correct radii | |

### Input area

| Check | Pass/Fail |
|---|---|
| Input wrapper: `#f0f0f0` bg, 0.5px `#e0e0e0` border, 16px radius | |
| Input text 15px DM Sans | |
| Placeholder text `#bbbbbb` | |
| Send button pinned inside right of input wrapper | |
| Input area never scrolls out of view | |

### Pills (idle state only)

| Check | Pass/Fail |
|---|---|
| Pills appear below input on idle | |
| Pills disappear after first message is sent | |
| Pill: 11px text, `#666`, 5px 11px padding, 14px radius, 0.5px `#e0e0e0` border | |
| Pill hover: `#f0f0f0` bg, `#000` text | |
| Clicking pill sends that text as a message | |

---

## Section 4 — All 11 widget states

For each state, trigger it and compare visually against the design guideline.

### State 1 — Idle

| Check | Pass/Fail |
|---|---|
| No messages rendered in message area | |
| Input empty, placeholder shows greeting text | |
| Send button EMPTY | |
| Pills visible below input | |
| Widget is compact (no large empty message area gap) | |

### State 2 — Visitor typing

| Check | Pass/Fail |
|---|---|
| Send button switches to ACTIVE immediately on first keystroke | |
| Send button returns to EMPTY when input is cleared | |
| Enter key sends message | |

### State 3 — Agent thinking

| Check | Pass/Fail |
|---|---|
| Visitor bubble appears with sent text | |
| Greeting ("Hi! How can I help you today?") appears above visitor bubble | |
| Typing indicator shows: 3 dots, animated pulse, 5px diameter, `#bbbbbb` | |
| Dot animation: stagger 0.2s between each dot | |
| Input disabled, placeholder "Waiting for response..." | |
| Send button DISABLED | |
| Pills hidden | |

### State 4 — Active conversation

| Check | Pass/Fail |
|---|---|
| Agent response replaces typing indicator | |
| Input re-enables, send button EMPTY | |
| Placeholder resets to "Type a message..." | |
| Multiple turns render correctly (alternating agent/visitor) | |
| All previous messages visible (not hidden) | |

### State 5 — Long conversation (scroll)

| Check | Pass/Fail |
|---|---|
| At desktop: message area caps at 400px, scrollbar appears | |
| At mobile (<480px): message area caps at 50vh | |
| Scrollbar: 3px wide, `#dddddd` thumb, transparent track | |
| Input area remains pinned below message area | |
| New messages auto-scroll to bottom when content overflows | |
| When `dynamicHeight=1`: max-height is removed, widget grows freely (no internal scroll for short convos) | |

### State 6 — Knowledge boundary

| Check | Pass/Fail |
|---|---|
| Agent message includes redirect to human | |
| Amber banner appears below agent bubble: `#faeeda` bg, `#854f0b` text, 8px radius | |
| Banner text: "Connect with team:" + prompt | |
| Agent does NOT hallucinate an answer | |

### State 7 — Contact captured

| Check | Pass/Fail |
|---|---|
| Send a message containing an email or phone number | |
| Agent acknowledges naturally | |
| No visible indicator to visitor (internal only) | |
| Conversation continues normally after capture | |

### State 8 — Idle nudge

| Check | Pass/Fail |
|---|---|
| After 60s silence, nudge appears | |
| Nudge is muted italic text (NOT a chat bubble) | |
| Nudge text: `#888888`, italic, 12px | |
| Only one nudge per conversation | |

### State 9 — Error

| Check | Pass/Fail |
|---|---|
| Error banner: `#fcebeb` bg, `#a32d2d` text, 8px radius | |
| Input stays active for retry | |
| Error disappears on next successful send | |
| Auto-retry fires once silently (2s delay) before showing error | |

### State 10 — Returning visitor

| Check | Pass/Fail |
|---|---|
| Previous messages render at ~55% opacity | |
| "Previous conversation" label with clock icon at top | |
| Label style: 11px, `#888`, `#fafafa` bg, `#e0e0e0` borders | |
| Input placeholder: "Continue or start new..." or similar | |

### State 11 — Conversation complete

| Check | Pass/Fail |
|---|---|
| Agent sign-off message renders | |
| Complete banner: `#fafafa` bg, `#888` text, `#0f6e56` accent | |
| Banner text: "Conversation ended — lead brief sent" | |
| Input disabled | |
| After 30s: placeholder changes to "Start a new conversation..." | |

---

## Section 5 — Responsive behavior

Run at three widths: 1280px (desktop), 544px (wide-narrow boundary), 375px (mobile).

| Check | 1280px | 544px | 375px |
|---|---|---|---|
| Widget max-width 600px, centered | | N/A | N/A |
| Widget fills parent container width | ✓ baseline | | |
| Message area max-height 400px (with dynamicHeight=0) | | | N/A |
| Message area max-height 50vh (with dynamicHeight=0) | N/A | N/A | |
| Input font-size 16px (prevents iOS zoom) | N/A | N/A | |
| Widget border-radius 12px | | | |
| Widget border-radius 0 if full-bleed mobile | N/A | N/A | |
| Pills wrap correctly at narrow width | | | |
| No horizontal overflow or scroll | | | |
| After sending a message: all content visible without page scroll | | | |

---

## Section 6 — Platform compatibility matrix

For each platform, embed the widget using Tier 1 (iframe) and run this checklist.

### Platforms to test

- Plain HTML page (baseline)
- Webflow
- WordPress (default theme)
- Wix
- Squarespace
- Notion (embed block)
- Google Sites

### Checks per platform

| Check | Notes |
|---|---|
| Widget renders correctly at desktop width | |
| Widget renders correctly at mobile width | |
| Dynamic height resize works (iframe grows with conversation) | postMessage listener must be added to parent |
| Page does not scroll unexpectedly when iframe resizes | scrollY preserve fix in listener |
| Dark mode on host site does not bleed into widget | widget must stay light |
| Host site fonts do not override widget fonts | DM Sans loaded inside iframe, isolated |
| Host site CSS does not leak into iframe | iframe is sandboxed from host styles |
| `X-Frame-Options: ALLOWALL` header present on `/widget/*` | Verify in Network tab → Response Headers |
| `frame-ancestors *` CSP header present | Same as above |
| Widget border is visible (not clipped by host overflow rules) | |
| Widget border-radius renders correctly | Some hosts reset `overflow: hidden` |

### Known platform-specific risks

| Platform | Risk | Mitigation |
|---|---|---|
| Wix | May inject its own font CSS into all iframes on same domain | Widget fonts load from Google Fonts — isolated in iframe |
| WordPress | Theme CSS may interfere IF using inline/div embed (Tier 2). Tier 1 iframe is safe. | Use Tier 1 for now |
| Webflow | `overflow: hidden` on parent containers can clip widget border-radius | Wrap iframe in a div with explicit overflow |
| Squarespace | Some templates force dark mode on embedded content | Verify `color-scheme: light` on widget root |
| Notion | Notion embeds strip `postMessage` in some contexts | Dynamic height may not work — test with fixed height fallback |
| iOS Safari | Font size < 16px triggers auto-zoom on input focus | Input font is 16px on mobile — verify no zoom |
| iOS Safari | `scrollY` preserve trick may not work in all scroll contexts | Test scroll behavior after agent responds on real iPhone |

---

## Section 7 — Dynamic height (iframe resize)

This is the most fragile behavior across platforms.

| Check | Pass/Fail |
|---|---|
| On load: iframe height matches idle widget height | |
| After first message sent: iframe grows to fit greeting + visitor bubble + thinking dots | |
| After agent responds: iframe grows to fit full conversation | |
| No page scroll occurs when iframe height changes | |
| On long conversation: iframe grows unbounded (no internal scroll) when dynamicHeight=1 | |
| On long conversation: internal scroll activates correctly when dynamicHeight=0 | |
| `postMessage` type is `contextus:resize` with `height` in px | Inspect in DevTools → Console |
| Parent listener saves and restores `window.scrollY` before/after height change | |
| `ResizeObserver` on widget element fires on every layout change | |

---

## Section 8 — Edge cases

| Scenario | Expected behavior | Pass/Fail |
|---|---|---|
| Send button clicked with empty input | Nothing happens | |
| Enter key pressed with empty input | Nothing happens | |
| Very long visitor message (200+ chars) | Bubble wraps, no overflow outside container | |
| Very long agent response (300+ chars) | Text wraps, widget grows | |
| Rapid clicking send button | Only one message sent (isThinking guard) | |
| Multiple pill clicks quickly | Only first click registers | |
| Widget at 320px min-width | No horizontal overflow | |
| Special characters in message (&, <, >, ") | Rendered as text, not HTML | |
| Widget inside a CSS `transform` parent | BCR height still correct (getBoundingClientRect accounts for transforms) | |
| Host page has `overflow: hidden` on body | Verify dynamic height resize still works | |

---

## Audit sign-off

| Section | Auditor | Date | Result |
|---|---|---|---|
| 1 — Brand tokens | | | |
| 2 — Send button states | | | |
| 3 — Widget anatomy | | | |
| 4 — Widget states (11) | | | |
| 5 — Responsive | | | |
| 6 — Platform compatibility | | | |
| 7 — Dynamic height | | | |
| 8 — Edge cases | | | |

**Overall:** ☐ Pass  ☐ Pass with notes  ☐ Fail

**Notes:**

