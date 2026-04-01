# Phase A — Crawl-Generated Pills (Merged Plan)

> Combined from Claude plan + GLM-5 plan. Takes GLM-5's categorized pill model and
> priority selection logic, plus Claude's single-round-trip session pre-creation.

---

## Problem

Pills are hardcoded in `widget.js` as contextus-specific questions:
```js
pills: ['How can you help?', 'Pricing & plans', 'How do I embed this?']
```
These are meaningless for any other business. A restaurant gets the same pills as a law firm.

---

## Flow

```
POST /api/crawl
  → crawl + chunk site
  → generate_company_profile()
      → LLM returns pill_suggestions: { service_questions, gap_questions, industry_questions }
  → select_pills() picks best 3 by priority
  → KB stored with suggested_pills: ["What are your prices?", "What's included?", "Do you work with SMBs?"]

widget.html loads
  → POST /api/session   ← returns { session_id, pills } in one round trip
  → window.__ctxSessionId = session_id  (pre-cached, eliminates first-message delay)
  → ContextusWidget.init({ pills })

Widget shows business-specific pills instantly
```

---

## Files to Change

| File | Change |
|------|--------|
| `backend/app/models.py` | Add `PillSuggestions` model, update `CompanyProfile` + `KnowledgeBase` |
| `backend/app/services/llm.py` | Add pill categories to prompt, add `select_pills()` + `generate_fallback_pills()` |
| `backend/app/routers/crawl.py` | Call `select_pills()` after profile generation, store on KB |
| `backend/app/routers/session.py` | Return `pills` alongside `session_id` |
| `widget/widget.html` | Async init: fetch session → extract pills → pass to `ContextusWidget.init` |
| `widget/widget.js` | Read pre-created session from `window.__ctxSessionId` |

---

## Step 1 — `backend/app/models.py`

```python
class PillSuggestions(BaseModel):
    """LLM-generated pill questions organized by category."""
    service_questions: list[str] = []   # questions about main services
    gap_questions: list[str] = []       # questions filling missing website info
    industry_questions: list[str] = []  # niche/industry-specific question


class CompanyProfile(BaseModel):
    name: str
    industry: str
    services: list[str]
    location: str | None = None
    contact: str | None = None
    summary: str
    gaps: list[str]
    pill_suggestions: PillSuggestions | None = None  # ← new


class KnowledgeBase(BaseModel):
    job_id: str
    status: Literal['crawling', 'analyzing', 'complete', 'failed']
    progress: str = ''
    pages_found: int = 0
    quality_tier: Literal['rich', 'thin', 'empty'] | None = None
    company_profile: CompanyProfile | None = None
    chunks: list[Chunk] = []
    suggested_pills: list[str] = []  # ← new: final 3 pills, ready for widget
    created_at: int
```

---

## Step 2 — `backend/app/services/llm.py`

**2a. Update profile system prompt** — extend JSON schema:

```json
"pill_suggestions": {
  "service_questions": ["2 natural questions about their main services (max 6 words each)"],
  "gap_questions": ["1 question addressing the most important missing info"],
  "industry_questions": ["1 niche-specific question a real visitor would ask"]
}
```

Prompt rules to add:
- Max 6 words per pill
- Sound conversational, like something a real person types
- service_questions based on `services[]`
- gap_questions based on `gaps[]`
- If services are thin, still generate plausible questions from the summary

**2b. Add `select_pills()` with priority logic:**

```python
def select_pills(pill_suggestions: PillSuggestions | None) -> list[str]:
    """
    Priority: gap questions → service questions → industry questions → fallback.
    Gap questions first — they address missing info visitors most want to know.
    """
    if not pill_suggestions:
        return generate_fallback_pills()

    pills = []

    # 1. One gap question (highest value — addresses missing website info)
    if pill_suggestions.gap_questions:
        pills.append(pill_suggestions.gap_questions[0])

    # 2. Service questions to fill remaining slots
    remaining = 3 - len(pills)
    pills.extend(pill_suggestions.service_questions[:remaining])

    # 3. Industry question if still under 3
    if len(pills) < 3 and pill_suggestions.industry_questions:
        pills.append(pill_suggestions.industry_questions[0])

    # 4. Generic fallback for any remaining slots
    for fallback in generate_fallback_pills():
        if len(pills) >= 3:
            break
        if fallback not in pills:
            pills.append(fallback)

    return pills[:3]


def generate_fallback_pills() -> list[str]:
    return [
        "What services do you offer?",
        "How can you help me?",
        "How do I contact you?",
    ]
```

---

## Step 3 — `backend/app/routers/crawl.py`

After profile generation in `run_crawl_job`, add:

```python
from app.services.llm import select_pills

# existing:
company_profile = generate_company_profile(chunks, url)
kb.company_profile = company_profile

# new:
kb.suggested_pills = select_pills(company_profile.pill_suggestions)
```

---

## Step 4 — `backend/app/routers/session.py`

Update `SessionResponse` and endpoint to include pills:

```python
class SessionResponse(BaseModel):
    session_id: str
    pills: list[str] = []
```

```python
# Load KB to get pills
kb = await get_knowledge_base(body.knowledge_base_id)
pills = kb.suggested_pills if kb else []

return SessionResponse(session_id=session_id, pills=pills)
```

---

## Step 5 — `widget/widget.html`

Switch from sync init to async — fetch session (gets pills + pre-caches session ID):

```js
(async function () {
  var params = new URLSearchParams(location.search);
  var transparent = params.get('transparent') === '1';
  if (transparent) document.body.classList.add('transparent');

  var apiUrl = params.get('apiUrl') || '';
  var knowledgeBaseId = params.get('knowledgeBaseId') || '';
  var pills = null;

  if (apiUrl && knowledgeBaseId) {
    try {
      var sr = await fetch(apiUrl + '/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ knowledge_base_id: knowledgeBaseId }),
      });
      if (sr.ok) {
        var data = await sr.json();
        window.__ctxSessionId = data.session_id;  // pre-cache: no delay on first message
        if (data.pills && data.pills.length) pills = data.pills;
      }
    } catch (e) { /* fall through to defaults */ }
  }

  ContextusWidget.init({
    root: document.getElementById('contextus-root'),
    name: params.get('name') || 'contextus',
    greeting: params.get('greeting') || 'Ask us anything...',
    lang: params.get('lang') || 'auto',
    transparent: transparent,
    dynamicHeight: params.get('dynamicHeight') === '1',
    apiUrl: apiUrl,
    knowledgeBaseId: knowledgeBaseId,
    pills: pills || ['What services do you offer?', 'How can you help me?', 'How do I contact you?'],
  });
})();
```

---

## Step 6 — `widget/widget.js`

In `callBackend()`, use the pre-cached session before falling back to creating one:

```js
if (!state.sessionId) {
  if (window.__ctxSessionId) {
    state.sessionId = window.__ctxSessionId;
    window.__ctxSessionId = null;
  } else {
    // existing POST /api/session fallback logic...
  }
}
```

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| API timeout / error | Widget uses default pills, session created on first message |
| `suggested_pills` empty | `select_pills()` returns `generate_fallback_pills()` |
| Only 1 service found | 1 service + 1 gap + 1 industry/fallback |
| No gaps identified | 2 service + 1 industry question |
| Thin/empty content | Fallback pills |
| Widget without `knowledgeBaseId` | Fallback pills, no session pre-created |
| LLM returns malformed JSON | `pill_suggestions` is None → fallback pills |
| Old KB (no `suggested_pills`) | Empty list → widget falls back to defaults |

---

## Verification

1. Re-seed demo KB: `curl -X POST https://contextus-2d16.onrender.com/api/crawl/demo`
2. Wait: `curl https://contextus-2d16.onrender.com/api/crawl/demo` → check `suggested_pills: [...]`
3. Create session: `POST /api/session { "knowledge_base_id": "demo" }` → check `pills: [...]` in response
4. Open landing page → hero widget shows crawl-based pills
5. Verify first message sends instantly (no session creation delay — pre-cached)
6. Test fallback: remove `knowledgeBaseId` from iframe src → default pills show

---

*Phase B (dynamic follow-up pills per response) and Phase C (behavioral filtering) documented separately.*
