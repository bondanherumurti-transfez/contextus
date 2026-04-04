# /try Page — Real Backend Integration Plan

## Context

The `/try` page is a fully working mockup with a hardcoded state machine (SCENARIOS object, fake timers, regex responses). All states — crawling, summary, chat, brief — are simulated. This plan wires every state to the real backend API, replacing mocks with live calls while keeping the same visual flow the user approved.

Backend API is live at `https://contextus-2d16.onrender.com`. All endpoints are ready.

---

## Files to Change

| File | Change |
|------|--------|
| `try/index.html` | Replace all mock logic with real API calls |
| `widget/widget.html` | postMessage `session_id` back to parent after session creation |
| `widget/widget.js` | postMessage `contextus:message_sent` to parent on each message |

---

## Step 1 — `widget/widget.js`: postMessage on each message sent

In `callBackend()`, after incrementing or tracking message count, add:

```js
window.parent.postMessage({ type: 'contextus:message_sent' }, '*');
```

Call this right before or after the SSE fetch starts — once per user message. The try page listens and increments its own `msgCount` to trigger the brief hint after 3 messages.

---

## Step 2 — `widget/widget.html`: postMessage session_id to parent

After session creation succeeds in the async init IIFE, add:

```js
if (data.session_id) {
  window.parent.postMessage({ type: 'contextus:session_ready', session_id: data.session_id }, '*');
}
```

The try page listens for this event and stores `sessionId` for brief generation. This avoids the try page needing to create its own session separately.

---

## Step 3 — `try/index.html`: replace mock state machine

### 3a — Config

Add at the top of the script block:
```js
const API_URL = 'https://contextus-2d16.onrender.com';
```

Remove the entire `SCENARIOS` object and all references to `currentScenario`.

### 3b — State variables

Replace current mock vars with:
```js
let jobId = null;
let sessionId = null;
let msgCount = 0;
let pollTimer = null;
```

### 3c — `submitUrl()`: call real crawl API

```js
function submitUrl() {
  const urlInput = document.getElementById('url-input');
  // ... validation unchanged ...
  removeIdleInputs();

  fetch(API_URL + '/api/crawl', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: val })
  })
  .then(r => {
    if (r.status === 429) throw Object.assign(new Error('rate_limit'));
    if (!r.ok) throw new Error('crawl_failed');
    return r.json();
  })
  .then(data => {
    jobId = data.job_id;
    startCrawl(val);   // transitions to crawling state, starts polling
  })
  .catch(err => {
    restoreIdleInputs();
    showUrlError(err.message === 'rate_limit'
      ? 'Too many requests — please wait an hour before trying again.'
      : 'Could not start crawl. Please check the URL and try again.');
  });
}
```

### 3d — `startCrawl()`: poll real status

Replace fake setTimeout chain with real polling every 2s:

```js
function startCrawl(domain) {
  document.getElementById('crawl-domain').textContent =
    domain.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
  resetSteps();
  setStep('cs-find', 'active');
  setProgress(8);
  show('crawling');

  let elapsed = 0;
  pollTimer = setInterval(async () => {
    elapsed += 2;
    if (elapsed > 90) {
      clearInterval(pollTimer);
      showCrawlError('Crawl timed out — the site may be too slow to read. Try a different URL.');
      return;
    }

    try {
      const r = await fetch(API_URL + '/api/crawl/' + jobId);
      if (!r.ok) return;
      const kb = await r.json();

      updateCrawlProgress(kb);

      if (kb.status === 'complete') {
        clearInterval(pollTimer);
        onCrawlComplete(kb);
      } else if (kb.status === 'failed') {
        clearInterval(pollTimer);
        showCrawlError('We couldn\'t read this site. It may block automated access.');
      }
    } catch (e) { /* keep polling */ }
  }, 2000);
}
```

Progress mapping from `kb.status` and `kb.pages_found`:
```js
function updateCrawlProgress(kb) {
  const pagesTag = document.getElementById('pages-tag');
  if (kb.pages_found > 0) {
    pagesTag.textContent = `— ${kb.pages_found} page${kb.pages_found > 1 ? 's' : ''} found`;
    pagesTag.style.opacity = '1';
  }
  if (kb.status === 'crawling') {
    setStep('cs-find', 'active'); setProgress(25);
  } else if (kb.status === 'analyzing') {
    setStep('cs-find', 'done'); setStep('cs-read', 'active'); setProgress(55);
  }
}
```

### 3e — `onCrawlComplete(kb)`: populate summary from real data

```js
function onCrawlComplete(kb) {
  const p = kb.company_profile;

  if (!p || kb.quality_tier === 'empty') {
    show('empty');
    return;
  }

  document.getElementById('sc-name').textContent = p.name;
  document.getElementById('sc-meta').textContent =
    [kb.pages_found + ' pages', p.industry, p.location].filter(Boolean).join(' · ');
  document.getElementById('sc-about').textContent = p.summary;

  const servicesTags = document.getElementById('sc-services');
  servicesTags.innerHTML = p.services.map(s => `<span class="svc-tag">${esc(s)}</span>`).join('');

  const gapsList = document.getElementById('sc-gaps');
  if (p.gaps && p.gaps.length) {
    gapsList.innerHTML = p.gaps.map(g => `<li>${esc(g)}</li>`).join('');
    document.getElementById('sc-gaps-section').style.display = '';
  } else {
    document.getElementById('sc-gaps-section').style.display = 'none';
  }

  document.getElementById('thin-warning').style.display =
    kb.quality_tier === 'thin' ? '' : 'none';

  show('summary');
}
```

### 3f — Chat state: real widget iframe

When "Chat with your assistant" is clicked, build and inject the real widget iframe instead of the mock widget. Store `kb` from `onCrawlComplete` in a closure variable so `startChat()` can access it:

```js
function startChat() {
  const p = currentKb.company_profile;
  const name = encodeURIComponent(p.name);
  const greeting = encodeURIComponent('Ask anything about ' + p.name + '...');
  const src = `/widget/widget.html?apiUrl=${encodeURIComponent(API_URL)}`
    + `&knowledgeBaseId=${encodeURIComponent(jobId)}`
    + `&name=${name}&greeting=${greeting}&transparent=0&dynamicHeight=1`;

  const container = document.getElementById('widget-iframe-container');
  container.innerHTML = `<iframe src="${src}" width="100%" height="500"
    frameborder="0" scrolling="no" style="border:none;display:block;border-radius:12px"></iframe>`;

  document.getElementById('chat-co').textContent = p.name;
  show('chat');
}
```

Add `let currentKb = null;` to state variables and set `currentKb = kb;` in `onCrawlComplete`.

### 3g — Listen for widget postMessages

```js
window.addEventListener('message', function(e) {
  if (!e.data) return;
  if (e.data.type === 'contextus:session_ready') {
    sessionId = e.data.session_id;
  }
  if (e.data.type === 'contextus:message_sent') {
    msgCount++;
    if (msgCount >= 3) {
      document.getElementById('brief-hint').classList.add('show');
    }
  }
  if (e.data.type === 'contextus:resize') {
    const iframe = document.querySelector('#widget-iframe-container iframe');
    if (iframe) iframe.style.height = e.data.height + 'px';
  }
});
```

### 3h — Brief generation: call real API

```js
async function generateBrief() {
  if (!sessionId) {
    document.getElementById('brief-hint').style.display = 'none';
    return;
  }
  document.getElementById('brief-hint-btn').textContent = 'Generating...';
  document.getElementById('brief-hint-btn').disabled = true;

  try {
    const r = await fetch(API_URL + '/api/brief/' + sessionId, { method: 'POST' });
    if (!r.ok) throw new Error();
    const brief = await r.json();
    renderBrief(brief);
    show('brief');
  } catch {
    document.getElementById('brief-hint').style.display = 'none';
  }
}

function renderBrief(b) {
  document.getElementById('br-who').textContent = b.who;
  document.getElementById('br-need').textContent = b.need;
  document.getElementById('br-signals').textContent = b.signals;
  document.getElementById('br-openqs').textContent = b.open_questions;
  document.getElementById('br-approach').textContent = b.suggested_approach;
  const badge = document.getElementById('br-quality');
  badge.textContent = b.quality_score.charAt(0).toUpperCase() + b.quality_score.slice(1);
  badge.className = 'qbadge ' + b.quality_score;
  const contact = b.contact;
  const contactEl = document.getElementById('br-contact-row');
  if (contact && (contact.email || contact.phone || contact.whatsapp)) {
    document.getElementById('br-contact').textContent =
      contact.email || contact.phone || contact.whatsapp;
    contactEl.style.display = '';
  } else {
    contactEl.style.display = 'none';
  }
}
```

### 3i — Empty state: enrich with manual form

When user submits the manual entry form, call `/api/crawl/{job_id}/enrich`:

```js
async function submitManualForm() {
  const answers = {
    'What does your business do?': document.getElementById('mf-biz').value,
    'Who are your customers?': document.getElementById('mf-cust').value,
    'What do you want visitors to do?': document.getElementById('mf-cta').value,
  };
  const r = await fetch(API_URL + '/api/crawl/' + jobId + '/enrich', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers })
  });
  if (r.ok) {
    const profile = await r.json();
    onCrawlComplete({ company_profile: profile, quality_tier: 'thin', pages_found: 0 });
  }
}
```

### 3j — `reset()`: clean up

```js
function reset() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  jobId = null;
  sessionId = null;
  msgCount = 0;
  currentKb = null;
  document.getElementById('widget-iframe-container').innerHTML = '';
  document.getElementById('brief-hint').classList.remove('show');
  document.getElementById('manual-form').classList.remove('show');
  document.getElementById('manual-entry-btn').style.display = '';
  resetSteps();
  restoreIdleInputs();
  show('idle');
}
```

---

## HTML changes in `try/index.html`

The mock widget HTML (pills, fake messages, fake input) in the chat state gets replaced with a simple container:

```html
<!-- STATE 3b — CHAT -->
<div class="state" id="s-chat">
  <div class="chat-header">
    <span class="chat-co" id="chat-co"></span>
    <button class="btn-s" onclick="show('summary')">← Back</button>
  </div>
  <div id="widget-iframe-container"></div>
  <div class="brief-hint" id="brief-hint">
    <p>Based on this conversation, contextus would generate a lead brief.</p>
    <button class="btn-p" id="brief-hint-btn" onclick="generateBrief()">See lead brief →</button>
  </div>
  <p class="widget-caption">This is how it would look on your site.</p>
</div>
```

Brief card element IDs (must match `renderBrief()` targets):
`br-who`, `br-need`, `br-signals`, `br-openqs`, `br-approach`, `br-quality`, `br-contact`, `br-contact-row`

---

## Error States

| Scenario | Behavior |
|----------|----------|
| 429 on crawl | Inline error "Too many requests — try again in an hour" |
| Crawl `failed` | `showCrawlError()` with retry button back to idle |
| Crawl timeout (>90s) | Same as failed |
| `onCrawlComplete` with no profile | Treat as empty tier |
| Session postMessage never arrives | `sessionId` stays null; brief button hidden silently |
| Brief fails / sessionId null | Hide brief hint silently |

---

## Verification

1. Submit a real URL → see real crawl steps update, pages found counter increment
2. `complete` received → summary card shows real company name, services, gaps
3. Click "Chat with your assistant" → real widget iframe loads with KB-generated pills
4. Send 3+ messages → brief hint appears below widget
5. Click "See lead brief" → real brief card renders with data from conversation
6. Submit a thin URL (one-page site) → thin warning shown in summary
7. Submit a blocked URL → empty state shown; manual form works; submitting transitions to chat
8. Click "Try another URL" → full reset, input restored, clean state
9. Hit rate limit → friendly inline error, no state transition
