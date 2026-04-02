# contextus — /join Waitlist Page Plan

## Context

The brief card on `/try` has "Add this to my site →" currently linking to a dead anchor. This plan wires it to a dedicated `/join` page — the highest-intent moment in the product.

The page collects name, email, website (pre-filled from /try), and phone, then surfaces the contextus widget to gather goal, agent behavior, business type, and timeline through natural conversation. Everything posts to a Notion database.

**What the user confirmed:**
- CTA placement: after brief on /try only
- Storage: Notion
- Widget asks: goal, agent behavior, business type, timeline

---

## User flow

```
/try brief → "Add this to my site →"
  ↓
/join?website=https://their-site.com
  ↓
[Step 1 — Form]
  Name (required)
  Email (required)
  Website (pre-filled from ?website= param, required)
  Phone / WhatsApp (optional)
  "Continue →" button
  ↓ POST /api/waitlist/start → { session_id }
  ↓
[Step 2 — Chat]
  contextus widget loads with session pre-loaded
  Widget knows: name + website, asks about:
    1. Business type
    2. Goal for placing widget
    3. How agent should behave
    4. Timeline / urgency
  "Submit →" button always visible — can skip chat
  ↓ POST /api/waitlist/submit → Notion
  ↓
[Step 3 — Done]
  "You're on the list."
  "We'll reach out at {email} when your slot is ready."
```

---

## Files to create / modify

| File | Action |
|------|--------|
| `join/index.html` | Create — full waitlist page |
| `try/index.html` | Modify — wire "Add this to my site →" to `/join?website={url}` |
| `widget/widget.html` | Modify — accept `sessionId` URL param to skip session creation |
| `backend/app/routers/waitlist.py` | Create — `/api/waitlist/start` + `/api/waitlist/submit` |
| `backend/app/main.py` | Modify — include waitlist router |
| `backend/app/services/notion.py` | Create — Notion API client |
| `backend/app/services/llm.py` | Modify — add waitlist system prompt + extract_waitlist_context() |
| `backend/.env.example` | Modify — add NOTION_TOKEN, NOTION_DB_WAITLIST |

---

## Backend

### `POST /api/waitlist/start`

**Request:**
```json
{ "name": "Bondan", "email": "bondan@finfloo.com", "website": "https://finfloo.com", "phone": "+628xxx" }
```

**What it does:**
1. Creates a `Session` against `kb_id = "demo"` with `contact_captured = True`
2. Stores prefill data in Redis at `waitlist:{session_id}` with 1hr TTL
3. Returns `{ "session_id": "..." }`

### `POST /api/waitlist/submit`

**Request:**
```json
{ "session_id": "abc123" }
```

**What it does:**
1. Reads prefill from `waitlist:{session_id}` Redis key
2. Loads session messages (if any conversation happened)
3. Runs `extract_waitlist_context(transcript)` — LLM extracts goal, agent_behavior, business_type, timeline from conversation
4. Posts full record to Notion
5. Returns `{ "status": "ok" }`

---

## `backend/app/services/notion.py`

```python
import os, httpx

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_VERSION = "2022-06-28"

async def post_waitlist_to_notion(data: dict):
    database_id = os.getenv("NOTION_DB_WAITLIST", "")
    if not NOTION_TOKEN or not database_id:
        return  # silently skip if not configured

    def txt(val):
        return [{"text": {"content": str(val or "—")}}]

    page = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name":           {"title": txt(data.get("name", "Unknown"))},
            "Email":          {"email": data.get("email") or None},
            "Website":        {"url": data.get("website") or None},
            "Phone":          {"rich_text": txt(data.get("phone"))},
            "Business Type":  {"rich_text": txt(data.get("business_type"))},
            "Goal":           {"rich_text": txt(data.get("goal"))},
            "Agent Behavior": {"rich_text": txt(data.get("agent_behavior"))},
            "Timeline":       {"rich_text": txt(data.get("timeline"))},
            "Session":        {"rich_text": txt(data.get("session_id"))},
        },
    }

    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.notion.com/v1/pages",
            json=page,
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
```

**Notion database properties to create manually:**
| Property | Type |
|----------|------|
| Name | Title |
| Email | Email |
| Website | URL |
| Phone | Text |
| Business Type | Text |
| Goal | Text |
| Agent Behavior | Text |
| Timeline | Text |
| Session | Text |

---

## `backend/app/services/llm.py` additions

### Waitlist system prompt

```python
def build_waitlist_system_prompt(name: str, website: str) -> str:
    return f"""You are the onboarding assistant for contextus — an AI widget that qualifies leads automatically for businesses.

You already know:
- Visitor name: {name}
- Their website: {website}

Your job is to warmly learn about their situation through natural conversation. Gather these four things in order:
1. What kind of business they run (industry, size, what they sell)
2. What their goal is for placing contextus on their site (lead gen, customer support, sales qualification, etc.)
3. How they'd like their agent to behave (formal/casual, topics to focus on, what to do when visitors ask about pricing, etc.)
4. Their timeline — when do they want this live?

Rules:
- Address them by first name
- Ask one question per turn, weave naturally into conversation
- If they say "I don't know" or skip a question, move on gracefully
- Answer questions about contextus if they ask
- After gathering the 4 points (or after they've skipped), say:
  "Perfect, {name} — you're all set. We'll be in touch soon to get contextus live on {website}. Keep an eye on {name.split()[0] if name else 'your'} inbox!"
- Keep responses short, warm, and human"""
```

### Context extraction

```python
def extract_waitlist_context(transcript: str) -> dict:
    """Extract business_type, goal, agent_behavior, timeline from conversation."""
    response = client.chat.completions.create(
        model=MODEL_PROFILE,
        messages=[
            {
                "role": "system",
                "content": (
                    'Extract from this conversation transcript as JSON: '
                    '{"business_type": "...", "goal": "...", "agent_behavior": "...", "timeline": "..."}. '
                    'Use empty string for anything not mentioned. Return JSON only.'
                ),
            },
            {"role": "user", "content": transcript},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    try:
        return extract_json(response.choices[0].message.content)
    except Exception:
        return {"business_type": "", "goal": "", "agent_behavior": "", "timeline": ""}
```

---

## `widget/widget.html` modification

In the init IIFE, check for `sessionId` URL param. If present, skip `POST /api/session` and use it directly — the session was pre-created by `/api/waitlist/start`.

```js
var providedSessionId = params.get('sessionId') || '';

if (apiUrl && knowledgeBaseId && !providedSessionId) {
  // existing session creation flow
  var sr = await fetch(apiUrl + '/api/session', { ... });
  if (sr.ok) {
    var data = await sr.json();
    window.__ctxSessionId = data.session_id;
    if (data.pills && data.pills.length) pills = data.pills;
    window.parent.postMessage({ type: 'contextus:session_ready', session_id: data.session_id }, '*');
  }
} else if (providedSessionId) {
  window.__ctxSessionId = providedSessionId;
  window.parent.postMessage({ type: 'contextus:session_ready', session_id: providedSessionId }, '*');
}
```

---

## `join/index.html`

### Structure

```
join/
└── index.html   (self-contained, same style as try/index.html)
```

Three states: `form` → `chat` → `done`

### Form state HTML

```html
<div id="s-form" class="state active">
  <p class="eyebrow">You saw it work.</p>
  <h1>Now let's get it on your site.</h1>
  <p class="sub">Leave your details — we'll set it up for you.</p>
  <div class="join-form">
    <input id="j-name"    type="text"  placeholder="Your name" autocomplete="name" />
    <input id="j-email"   type="email" placeholder="Email address" autocomplete="email" />
    <input id="j-website" type="url"   placeholder="https://your-site.com" />
    <input id="j-phone"   type="tel"   placeholder="Phone / WhatsApp (optional)" />
    <p id="j-err" class="err-msg" style="display:none"></p>
    <button id="j-submit" class="btn-p">Continue →</button>
  </div>
</div>
```

Pre-fill website on load:
```js
const ws = new URLSearchParams(location.search).get('website');
if (ws) document.getElementById('j-website').value = ws;
```

### Submit handler

```js
async function submitForm() {
  const name    = document.getElementById('j-name').value.trim();
  const email   = document.getElementById('j-email').value.trim();
  const website = document.getElementById('j-website').value.trim();
  const phone   = document.getElementById('j-phone').value.trim();

  if (!name || !email || !website) { showErr('Name, email, and website are required.'); return; }

  const btn = document.getElementById('j-submit');
  btn.textContent = 'Setting up...';
  btn.disabled = true;

  const res = await fetch(API_URL + '/api/waitlist/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, website, phone }),
  });

  if (!res.ok) { btn.textContent = 'Continue →'; btn.disabled = false; showErr('Something went wrong. Please try again.'); return; }

  const { session_id } = await res.json();
  currentSessionId = session_id;
  currentEmail = email;

  loadWidget(session_id, name, website);
  show('chat');
}
```

### Chat state HTML

```html
<div id="s-chat" class="state">
  <div id="join-widget-container"></div>
  <div class="join-chat-footer">
    <button id="j-done" class="btn-p" onclick="submitWaitlist()">Submit →</button>
    <p class="join-note">Skip the chat and just submit your details.</p>
  </div>
</div>
```

### loadWidget()

```js
function loadWidget(session_id, name, website) {
  const greeting = encodeURIComponent('Hi ' + name + '! Tell me about your business — I have a few quick questions.');
  const src = '/widget/widget.html'
    + '?apiUrl=' + encodeURIComponent(API_URL)
    + '&knowledgeBaseId=demo'
    + '&sessionId=' + encodeURIComponent(session_id)
    + '&greeting=' + greeting
    + '&transparent=0&dynamicHeight=1';

  const container = document.getElementById('join-widget-container');
  container.innerHTML = '<iframe src="' + src + '" width="100%" height="480" frameborder="0" scrolling="no" style="border:none;display:block;border-radius:12px"></iframe>';
}
```

### submitWaitlist()

```js
async function submitWaitlist() {
  const btn = document.getElementById('j-done');
  btn.textContent = 'Submitting...';
  btn.disabled = true;

  await fetch(API_URL + '/api/waitlist/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: currentSessionId }),
  });

  document.getElementById('done-email').textContent = currentEmail;
  show('done');
}
```

### Done state HTML

```html
<div id="s-done" class="state">
  <h1>You're on the list.</h1>
  <p class="sub">We'll reach out at <strong id="done-email"></strong> when your slot is ready.</p>
  <a href="/" class="btn-s">Back to contextus →</a>
</div>
```

---

## `try/index.html` modification

In `renderBrief()`, update the CTA link to pass the crawled URL:

```js
// Change static <a href="/#ea"> to dynamic
const addBtn = document.getElementById('add-to-site-btn');
if (addBtn) addBtn.href = '/join?website=' + encodeURIComponent(currentUrl);
```

Change the HTML from:
```html
<a href="/#ea" class="btn-p">Add this to my site →</a>
```
To:
```html
<a id="add-to-site-btn" href="/join" class="btn-p">Add this to my site →</a>
```

`currentUrl` is already tracked in state (the URL the user originally submitted).

---

## Environment variables

Add to Render dashboard and `.env.example`:
```
NOTION_TOKEN=secret_xxxx
NOTION_DB_WAITLIST=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # 32-char database ID from Notion URL
```

---

## Notion setup (manual, one-time)

1. Create a new database in Notion called "contextus waitlist"
2. Add properties: Name (title), Email (email), Website (url), Phone, Business Type, Goal, Agent Behavior, Timeline, Session (all text except the typed ones)
3. Go to notion.so/my-integrations → create integration → copy token → `NOTION_TOKEN`
4. Open the database → Share → Invite integration
5. Copy database ID from URL (32-char string after the workspace name) → `NOTION_DB_WAITLIST`

---

## Verification

1. Go to `/try`, crawl a URL, complete the chat, see the brief
2. Click "Add this to my site →" — should open `/join?website=https://...`
3. Website field is pre-filled; fill name, email, phone → Continue
4. Widget loads, greets by name, asks questions
5. Answer 1–2 questions then click Submit
6. Check Notion — row appears with name, email, website, phone + extracted goal/business type/behavior/timeline
7. Try skipping chat entirely — click Submit immediately after form → Notion row with form fields populated, context fields empty
8. Try going directly to `/join` without `?website=` — website field is blank, everything else works
