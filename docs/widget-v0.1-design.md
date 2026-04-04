# Widget v0.1 — Design Guideline

## Problem (observed in screenshots)

When the widget is embedded inline in a customer website (iframe inside a fixed-height container), the entire widget scrolls as one block. The header and input area scroll out of view as the conversation grows. The user is forced to scroll inside a cramped box to reach the input. This is unusable.

**Root cause:** `#contextus-widget` does not fill the iframe height. `.ctx-messages` has a hardcoded `max-height: 400px` instead of filling the remaining space. `html`, `body`, and `#contextus-root` have no explicit height, so the flex layout has nothing to stretch against.

---

## Widget v0.1 Layout Model

```
┌─────────────────────────────────┐  ← iframe boundary (fixed height, e.g. 480px)
│  ctx-header    (fixed, ~42px)   │  flex-shrink: 0
├─────────────────────────────────┤
│                                 │
│  ctx-messages  (scrollable)     │  flex: 1 — fills ALL remaining space
│                                 │  overflow-y: auto
│  new messages push to bottom    │  scrollTop = scrollHeight on every append
│                                 │
├─────────────────────────────────┤
│  ctx-input-area (fixed, ~70px)  │  flex-shrink: 0
└─────────────────────────────────┘
```

Three zones. Header and input never move. Messages fill the gap.

---

## Two-Phase Embed

A fixed iframe height on load shows a large empty box before any conversation. Instead the widget uses a **two-phase approach**:

**Phase 1 — idle (auto height)**
- No fixed height on the iframe
- Widget auto-sizes to header + pills + input
- Pills can wrap to multiple lines — no clipping
- Looks intentional, not like a broken empty box

**Phase 2 — expanded (480px)**
- Fires once on first message send
- `widget.js` fires `window.parent.postMessage({ type: 'contextus:expand' }, '*')`
- Parent script adds `.expanded` class to iframe → `height: 480px`
- Snap transition (no animation — CSS cannot transition from `auto` to fixed height)

### Embed snippet (customer pastes both)

Two-element pattern — wrapper handles animation, iframe handles layout:

```html
<style>
  /* Wrapper: animates via max-height (can transition, unlike height: auto) */
  #contextus-wrapper {
    max-height: 250px;          /* idle cap — generous enough for wrapped pills */
    overflow: hidden;
    transition: max-height 0.35s ease;
  }
  #contextus-wrapper.expanded {
    max-height: 520px;          /* slightly over iframe height to ensure no clipping */
  }

  /* Iframe: gets explicit height only when expanded (enables three-zone flex) */
  #contextus-iframe {
    border: none; display: block; width: 100%;
  }
  #contextus-wrapper.expanded #contextus-iframe {
    height: 480px;              /* adjust to taste */
  }
</style>

<div id="contextus-wrapper">
  <iframe
    id="contextus-iframe"
    src="https://getcontextus.dev/widget/widget.html?knowledgeBaseId=YOUR_KB_ID&apiUrl=https://contextus-2d16.onrender.com"
    frameborder="0"
  ></iframe>
</div>

<script>
  window.addEventListener('message', function(e) {
    if (e.data.type === 'contextus:expand') {
      document.getElementById('contextus-wrapper').classList.add('expanded');
    }
  });
</script>
```

### widget.js change (already implemented)

```js
// in sendMessage(), fires once on first message
if (!state.expanded) {
  state.expanded = true;
  window.parent.postMessage({ type: 'contextus:expand' }, '*');
}
```

| Property | Value | Note |
|----------|-------|------|
| Idle height | auto | Sizes to content — pills wrap freely |
| Expanded height | 480px | Customer can adjust in their CSS |
| Transition | none (snap) | CSS can't animate from `auto` → fixed |
| Expand trigger | First message sent | Fires once, never collapses back |
| postMessage type | `contextus:expand` | Implemented in widget.js |

---

## Common Implementation Pitfalls

### 1. Iframe height set unconditionally

**Wrong:**
```css
#widget-wrapper iframe {
  height: 480px;  /* PROBLEM: always 480px, clips idle content */
}
```

**Correct:**
```css
#widget-wrapper iframe {
  /* no height — auto-sizes to content in idle */
}
#widget-wrapper.expanded iframe {
  height: 480px;  /* only set after expand */
}
```

**Why it matters:** During idle phase, the iframe should auto-size to header + pills + input. If CSS sets a fixed height, the wrapper's `max-height: 250px` clips the content, making the widget look stuck even after `data-expanded="1"` is set.

### 2. Inline style.height not cleared on expand

The `contextus:resize` message sets inline `style.height` during idle phase. This inline style has higher specificity than CSS rules, so it blocks the `height: 480px` from taking effect.

**Wrong:**
```js
if (e.data.type === 'contextus:expand') {
  wrapper.classList.add('expanded');
  iframe.dataset.expanded = '1';
  // BUG: inline style.height="197px" still present
}
```

**Correct:**
```js
if (e.data.type === 'contextus:expand') {
  wrapper.classList.add('expanded');
  iframe.dataset.expanded = '1';
  iframe.style.height = '';  // clear inline height so CSS 480px applies
}
```

### 3. Missing contextus:expand listener

The widget fires `contextus:expand` on first message, but if the parent page doesn't listen for it, the expand never happens.

**Symptom:** Widget stays at idle height (~180px) even after first message. `data-expanded="1"` may be set but wrapper never gets `expanded` class.

### Real bugs fixed (2026-04-03)

**`/try` page (try/index.html):**
- CSS had `height: 480px` on iframe unconditionally → fixed to only apply on `.expanded`
- `contextus:expand` handler didn't clear inline `style.height` → added `iframe.style.height = ''`

**`/join` page (join/index.html):**
- No wrapper element with max-height animation → added wrapper div
- Fixed `height: 420px` on iframe → removed, now auto-sizes in idle
- No `contextus:expand` listener → added full handler
- Resize handler didn't check expanded state → added `!iframe.dataset.expanded` guard

---

## CSS Changes Required (widget.css + widget.html)

### 1. Full-height chain — html → body → root → widget

```css
/* widget.html */
html, body {
  height: 100%;
  overflow: hidden;
}

#contextus-root {
  width: 100%;
  height: 100%;       /* was missing */
}

/* widget.css */
#contextus-widget {
  width: 100%;
  height: 100%;       /* fill the root instead of sizing to content */
  max-width: 600px;
  /* remove: overflow: hidden */
  display: flex;
  flex-direction: column;
}
```

### 2. Messages — flex fill, no max-height

```css
.ctx-messages {
  flex: 1;            /* fills all space between header and input */
  min-height: 0;      /* CRITICAL — without this, flex child won't scroll */
  overflow-y: auto;
  padding: 14px;
  /* remove: max-height: 400px */
  scroll-behavior: smooth;
}
```

> `min-height: 0` is the non-obvious key fix — without it, a flex child won't scroll even with `overflow-y: auto` because its minimum height defaults to `auto` (content size).

### 3. Header and input — already correct, verify flex-shrink

```css
.ctx-header    { flex-shrink: 0; }  /* already set — keep */
.ctx-input-area { flex-shrink: 0; } /* already set — keep */
```

### 4. Remove mobile max-height override

```css
/* Remove this: */
@media (max-width: 480px) {
  .ctx-messages { max-height: 50vh; }
}
```

---

## JS — Auto-scroll to Bottom

### Scroll helpers

```js
function scrollToBottom(instant) {
  messagesEl.scrollTo({
    top: messagesEl.scrollHeight,
    behavior: instant ? 'instant' : 'smooth',
  });
}

function isNearBottom() {
  return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 80;
}
```

### When to call

| Event | Call |
|-------|------|
| Initial load / greeting | `scrollToBottom(instant)` |
| Visitor sends message | `scrollToBottom(instant)` — always snap |
| Typing dots appear | `scrollToBottom(instant)` |
| Each streaming token | `if (isNearBottom()) scrollToBottom()` — respects user scrolling up |
| Stream ends | `scrollToBottom(instant)` — final unconditional snap |
| User scrolled up | Show ↓ FAB button, hide when near bottom |

---

## Scroll-to-bottom FAB

When user scrolls up to re-read earlier messages, show a sticky ↓ button at the bottom-right of the message zone. Clicking snaps to bottom and hides the button.

```js
messagesEl.addEventListener('scroll', function() {
  fab.style.opacity = isNearBottom() ? '0' : '1';
  fab.style.pointerEvents = isNearBottom() ? 'none' : 'all';
});
```

---

## Responsive behaviour

- Inline embed: iframe sets outer boundary, widget fills it via `height: 100%` chain
- Floating button (widget.js): iframe positioned fixed bottom-right, explicit height set in JS — no change needed
- Mobile: consider `height: 100dvh` on the iframe container for full dynamic viewport height

---

## Implementation checklist

- [ ] `widget.html` — add `height: 100%` to `html`, `body`, `#contextus-root`
- [ ] `widget.css` — add `height: 100%` to `#contextus-widget`, remove `overflow: hidden`
- [ ] `widget.css` — replace `max-height: 400px` on `.ctx-messages` with `flex: 1; min-height: 0`
- [ ] `widget.css` — remove mobile `max-height: 50vh` override
- [ ] `widget.js` — add `scrollToBottom()` calls at message append, token stream, typing dots
- [ ] `widget.js` — add `isNearBottom()` guard on streaming tokens
- [ ] `widget.js` — add FAB show/hide on scroll event
- [x] `widget.js` — `contextus:expand` postMessage on first message (done)

---

## Mockup

Live mockup with annotated zones, scroll FAB demo, and two-phase expand demo:
`docs/contextus-widget-design-guideline.html` → sections 07 and 08
