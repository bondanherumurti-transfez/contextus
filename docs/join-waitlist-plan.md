# contextus — /join Waitlist Page Plan

## Context

The brief card on `/try` has "Add this to my site →" currently linking to a dead anchor. This plan wires it to a dedicated `/join` page — the highest-intent moment in the product.

The page collects name, email, website (pre-filled from /try), and phone, then surfaces the contextus widget to gather business type, goal, agent behavior, and timeline through natural conversation. The **agent drives the submission** — when it has gathered all needed info, it closes the chat and automatically posts everything to Notion. No manual submit button required (a skip fallback exists).

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
  Agent knows their name + website already
  Agent asks in order:
    1. What kind of business do you run?
    2. What's your goal for placing contextus?
    3. How do you want the agent to behave?
    4. When do you want this live?
  Can answer questions about contextus too
  When all info gathered → agent says closing phrase → /join page
  auto-detects it → POST /api/waitlist/submit → show done state
  "Skip →" button visible as fallback only
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
| `widget/widget.js` | Modify — include agent response text in `contextus:message_sent` postMessage |
| `widget/widget.html` | Modify — accept `sessionId` URL param to skip session creation |
| `backend/app/routers/waitlist.py` | Create — `/api/waitlist/start` + `/api/waitlist/submit` |
| `backend/app/main.py` | Modify — include waitlist router |
| `backend/app/services/notion.py` | Create — Notion API client |
| `backend/app/services/llm.py` | Modify — add waitlist system prompt + extract_waitlist_context() |
| `backend/.env.example` | Modify — add NOTION_TOKEN, NOTION_DB_WAITLIST |

---

## Key mechanism: agent-driven submission

The widget agent closes the conversation when it has gathered all 4 pieces of info. The `/join` page detects this and auto-submits.

**How it works:**

1. `widget.js` currently sends `contextus:message_sent` with no payload. Add the agent's full response text:
   ```js
   window.parent.postMessage({ type: 'contextus:message_sent', text: fullText }, '*');
   ```

2. The `/join` page listens for this event. If the text contains the closing signal (`WAITLIST_COMPLETE`), it triggers submission:
   ```js
   if (e.data.type === 'contextus:message_sent' && e.data.text?.includes('WAITLIST_COMPLETE')) {
     submitWaitlist();
   }
   ```

3. The waitlist system prompt instructs the agent to end its final message with `WAITLIST_COMPLETE` (hidden signal, not shown to user):
   ```
   When you have gathered all 4 pieces of info (or after the visitor has skipped),
   send your closing message and append exactly: WAITLIST_COMPLETE
   The /join page will detect this and handle the rest silently.
   ```

4. The `/join` page strips `WAITLIST_COMPLETE` before rendering — the user never sees it. (Widget.js renders the full text via SSE tokens, so stripping happens in the postMessage listener on the parent, not in the widget itself. The widget renders normally; the `/join` page just uses the signal from the postMessage.)

   Actually: since widget.js renders token-by-token via SSE, `WAITLIST_COMPLETE` will appear in the chat bubble. Fix: instruct the agent to put it on a new line as the very last token, and in the widget's `callBackend` function, strip any trailing `WAITLIST_COMPLETE` from rendered text.

   Cleaner fix: strip it in `widget.js` before rendering. After SSE stream ends, if `fullText` ends with `WAITLIST_COMPLETE`, remove it from the displayed message and send it in the postMessage.

---

## Backend

### `POST /api/waitlist/start`

**Request:**
```json
{ "name": "Bondan", "email": "bondan@finfloo.com", "website": "https://finfloo.com", "phone": "+628xxx" }
```

**What it does:**
1. Creates a `Session` against `kb_id = "demo"` with `contact_captured = True`
2. Stores prefill in Redis at `waitlist:{session_id}` (1hr TTL)
3. Returns `{ "session_id": "abc123" }`

### `POST /api/waitlist/submit`

**Request:**
```json
{ "session_id": "abc123" }
```

**What it does:**
1. Reads prefill from `waitlist:{session_id}` Redis key
2. Loads session messages
3. Calls `extract_waitlist_context(transcript)` — LLM extracts business_type, goal, agent_behavior, timeline
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
        return

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

**Notion database properties:**
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
    first = name.split()[0] if name else name
    return f"""You are the onboarding assistant for contextus — an AI widget that automatically qualifies leads for businesses.

You already know:
- Visitor name: {name}
- Their website: {website}

Your job: gather these 4 things through warm, natural conversation (one question at a time):
1. What kind of business they run (industry, what they sell)
2. Their goal for placing contextus (lead gen, support, sales qualification, etc.)
3. How they want the agent to behave (tone, topics to focus on, what to do when asked about pricing)
4. Their timeline (when do they want this live?)

Rules:
- Address them by first name ({first})
- Ask ONE question per turn
- If they skip or say "I don't know" — accept it and move on
- You can answer questions about contextus if they ask, then return to gathering info
- Keep responses short and warm

When you have gathered all 4 points (or the visitor has skipped all), send your closing message:
"Perfect, {first} — you're all set! We'll be in touch at your email to get contextus live on {website} soon. Looking forward to working with you."

Then on a new line append exactly this token (do not explain it): WAITLIST_COMPLETE"""
```

### Context extraction

```python
def extract_waitlist_context(transcript: str) -> dict:
    response = client.chat.completions.create(
        model=MODEL_PROFILE,
        messages=[
            {
                "role": "system",
                "content": (
                    'Extract from this conversation as JSON: '
                    '{"business_type": "...", "goal": "...", "agent_behavior": "...", "timeline": "..."}. '
                    'Empty string if not mentioned. Return JSON only.'
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

## `widget/widget.js` modification

In `callBackend()`, after the SSE stream ends and `fullText` is complete, before sending the postMessage:

```js
// Strip WAITLIST_COMPLETE signal from rendered text
let displayText = fullText;
const SIGNAL = 'WAITLIST_COMPLETE';
if (displayText.includes(SIGNAL)) {
  displayText = displayText.replace(SIGNAL, '').trimEnd();
  // Update the rendered message bubble to remove the signal
  // (update the last assistant message in the DOM)
}

window.parent.postMessage({
  type: 'contextus:message_sent',
  text: fullText  // send original (with signal) so parent can detect it
}, '*');
```

---

## `widget/widget.html` modification

In the init IIFE, check for `sessionId` URL param. If present, skip `POST /api/session`:

```js
var providedSessionId = params.get('sessionId') || '';

if (providedSessionId) {
  window.__ctxSessionId = providedSessionId;
  window.parent.postMessage({ type: 'contextus:session_ready', session_id: providedSessionId }, '*');
} else if (apiUrl && knowledgeBaseId) {
  // existing session creation flow
  var sr = await fetch(apiUrl + '/api/session', { ... });
  ...
}
```

---

## `join/index.html`

### States: `form` → `chat` → `done`

### Form state
- Inputs: name, email, website (pre-filled from `?website=`), phone
- Validation: name + email + website required
- Button shows spinner while POST /api/waitlist/start is in flight
- On success → show chat state

### Chat state
- Widget iframe built with: `sessionId`, `knowledgeBaseId=demo`, `apiUrl`, `greeting=Hi {name}...`, `dynamicHeight=1`
- postMessage listener:
  ```js
  window.addEventListener('message', e => {
    if (e.data?.type === 'contextus:message_sent' && e.data.text?.includes('WAITLIST_COMPLETE')) {
      submitWaitlist();  // auto-trigger
    }
    if (e.data?.type === 'contextus:resize') {
      // resize iframe
    }
  });
  ```
- "Skip →" link at bottom — calls `submitWaitlist()` manually

### Done state
- "You're on the list."
- "We'll reach out at {email} when your slot is ready."
- "← Back to contextus" link

---

## `try/index.html` modification

In the brief HTML, change:
```html
<a href="/#ea" class="btn-p">Add this to my site →</a>
```
To:
```html
<a id="add-to-site-btn" href="/join" class="btn-p">Add this to my site →</a>
```

In `renderBrief()`:
```js
const btn = document.getElementById('add-to-site-btn');
if (btn) btn.href = '/join?website=' + encodeURIComponent(currentUrl);
```

---

## Environment variables

```
NOTION_TOKEN=secret_xxxx
NOTION_DB_WAITLIST=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## Notion setup (one-time manual)

1. Create database "contextus waitlist" with the properties listed above
2. Go to notion.so/my-integrations → create integration → copy token → `NOTION_TOKEN`
3. Share the database with the integration
4. Copy database ID from URL (32-char string) → `NOTION_DB_WAITLIST`

---

## Verification

1. `/try` → crawl → brief → click "Add this to my site →"
2. `/join?website=...` opens with website pre-filled
3. Fill name, email, phone → Continue
4. Widget loads, greets by name, asks 4 questions naturally
5. After last answer: agent sends closing message → `WAITLIST_COMPLETE` detected → done state shows automatically
6. Check Notion — row with all fields populated
7. Test skip path: click "Skip →" immediately → Notion row with form fields only, context fields empty
8. Test direct `/join` (no `?website=`) → blank website field, everything else works
