# Chat Agent Optimization Plan

**Branch:** `feat/chat-agent-optimization`

---

## Step 1 — Fix LEAD_QUAL_GENERIC + temperature (current)

File: `backend/app/services/llm.py`. No schema changes, benefits all clients immediately.

### LEAD_QUAL_GENERIC changes

**Hard-terminate out-of-scope**
Rewrite STEP 1 exit so agent stops asking questions and stops offering "connect with the team" once scope mismatch is confirmed. Do NOT capture contact. Current "end gracefully" is too vague — model keeps the conversation alive.

**Add STEP 4: post-contact-capture shutdown**
After contact is collected, send one closing message, no new qualifying questions. Currently undefined — agent keeps generating filler for 3-5 exchanges after getting WhatsApp.

**Remove hardcoded English phrase**
`"By the way, who am I speaking with?"` leaks into Indonesian conversations. Replace with a language-agnostic instruction: ask naturally in whatever language the conversation is in.

**Add contact flip rule**
When visitor asks for company's WhatsApp or phone number, pivot to capturing visitor's contact: "Let me have our team reach out to you directly — what's the best WhatsApp to reach you?" Currently the agent deflects and loses the lead (Session 10 — Ajeng).

**Add pricing deadlock escalation**
If visitor asks about price/cost more than once with no KB answer available, stop deflecting and pivot to contact capture. Currently loops on "the team will give you details" until visitor drops off (Session 17).

### Temperature

Drop `temperature=0.7` → `0.4` in `stream_chat_response`. 0.7 is creative writing territory; a sales qualification bot needs consistency.

---

## Step 2 — Add `custom_instructions` to CompanyProfile ✓ Done

Files changed: `backend/app/models.py`, `backend/app/services/llm.py`, `backend/app/routers/crawl.py`.

- Added `custom_instructions: str | None = None` to `CompanyProfile` model
- Injected as a `# Client instructions` block in `build_chat_system_prompt`, placed just before the `{lead_qual}` block
- Exposed via a new dedicated endpoint `PATCH /api/crawl/{job_id}/custom-instructions` (Option B — separate endpoint, not bundled into enrich, so instructions can be updated without re-running enrichment)
- Persisted automatically via `model_dump_json()` — no database.py changes needed
- Pass `null` to clear instructions

---

## Step 3 — Language support for Finfloo (byproduct of Step 2)

No separate code needed. Once `custom_instructions` exists, set Finfloo's value to:

```
Always respond in Bahasa Indonesia. For the name ask use
"Ngomong-ngomong, boleh saya tahu nama Anda?" — never the English form.
```

Language support is config, not code. Do NOT build a `LEAD_QUAL_ID` variant or any language-specific prompt — that's a maintenance nightmare as the client base grows.

---

## Why this order (DRY rationale)

Language is one use case of `custom_instructions`. Building language support first would create redundant logic once `custom_instructions` lands. The mechanism comes first; language ships as a config value for free.

---

## Context: Finfloo chat log findings

Source: `debugging/sessions-2.json` (28 sessions, collected ~Apr 2026)

| Metric | Value |
|---|---|
| Contact captured | 6/28 (21%) |
| Brief sent | 4/28 (14%) |
| Avg messages/session | 7.6 |

**Key failures driving these changes:**

| Session | Problem |
|---|---|
| Session 21 | Scammer asked to "kirim ke rek BNI" (send to bank account) — agent still captured WhatsApp and sent brief |
| Session 27 | Visitor explicitly said they only want business capital (out of scope) — agent still qualified and sent brief |
| Session 17 | Visitor asked price 3 times — agent deflected every time, visitor dropped off |
| Session 10 | Visitor (Ajeng) asked for company's WhatsApp — agent deflected, no contact captured |
