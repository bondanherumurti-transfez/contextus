# Turnstile Plan — Bot Protection for /try and /join

## Goal

Prevent bots from abusing the two pages that trigger expensive operations:
- `/try` — Firecrawl credits (URL crawl) + LLM tokens (brief, chat)
- `/join` — LLM tokens (waitlist session + brief generation)

Tool: **Cloudflare Turnstile** (invisible mode, no visible CAPTCHA friction).

---

## Protection Points

| Page | Expensive action | Endpoint to gate |
|------|-----------------|------------------|
| `/try` | Firecrawl + LLM | `POST /api/crawl` |
| `/join` | LLM brief | `POST /api/waitlist/start` |

Everything downstream (chat, enrich, brief) is already gated behind a `session_id` that can only be created by passing these two entry points. Gating the entry point is sufficient.

### Out of scope

- `/widget/widget.html` sessions on customer sites — must remain frictionless for end users
- `POST /api/crawl/demo` and `/api/crawl/seed` — protect with `ADMIN_SECRET` instead
- Chat messages after session is created — not worth the friction

---

## Turnstile Widget Mode

Use **invisible** mode on both pages.

- No visible checkbox, no friction before the CTA
- Challenge is solved silently in the background
- Only shows a popup if Cloudflare genuinely cannot determine the user is human
- Users filling in a URL or a form are already demonstrating human intent — invisible is appropriate

---

## Environment Variables

| Variable | Where | Notes |
|----------|-------|-------|
| `CLOUDFLARE_TURNSTILE_SECRET` | Backend `.env` + Render | Never expose to client |
| `CLOUDFLARE_TURNSTILE_SITE_KEY` | Frontend (hardcoded in HTML) | Public, safe to expose |

### Local development

**Option A** (recommended): Skip verification entirely
```
CLOUDFLARE_TURNSTILE_SECRET=
```
Backend detects empty secret and skips verification.

**Option B**: Use Cloudflare test keys (always pass)
```
CLOUDFLARE_TURNSTILE_SECRET=1x0000000000000000000000000000000AA
CLOUDFLARE_TURNSTILE_SITE_KEY=1x00000000000000000000AA
```

### Production (Render)

Set `CLOUDFLARE_TURNSTILE_SECRET` in Render dashboard with real Cloudflare secret key.
Update the hardcoded site key in HTML before deployment.

---

## Frontend Implementation

### Key Pattern: Re-trigger on Invisible Challenge

When using invisible mode, if no token is cached, call `turnstile.execute()` and set a pending flag. The `onTurnstileSuccess` callback re-triggers the submission.

```js
var cfToken = '';
var submitPending = false;

function onTurnstileSuccess(token) {
  cfToken = token;
  if (submitPending) {
    submitPending = false;
    submitUrl(); // or submitForm()
  }
}

async function handleSubmit() {
  if (!cfToken) {
    submitPending = true;
    turnstile.execute('#cf-turnstile');
    return;
  }
  // ... proceed with fetch
  // After fetch completes (success or error):
  cfToken = '';
  turnstile.reset('#cf-turnstile');
}
```

### `/try/index.html`

**1. Add Turnstile script in `<head>`:**
```html
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
```

**2. Add invisible widget div after url-err-msg:**
```html
<div id="cf-turnstile" class="cf-turnstile" data-sitekey="1x00000000000000000000AA" data-callback="onTurnstileSuccess" data-size="invisible"></div>
```

**3. Send token in POST body:**
```js
body: JSON.stringify({ url: val, cf_turnstile_response: cfToken })
```

**4. Handle 403 response:**
```js
if (r.status === 403) {
  return r.json().then(data => { throw new Error(data.detail || 'forbidden'); });
}
```

---

### `/join/index.html`

Same pattern as `/try`:
1. Add Turnstile script in `<head>`
2. Add invisible widget div in form-footer (before submit button)
3. Add `onTurnstileSuccess` callback
4. Modify `submitForm()` to handle token
5. Reset token after request

---

## Backend Implementation

### `app/services/turnstile.py`

```python
import os
import httpx
import logging

logger = logging.getLogger(__name__)
TURNSTILE_SECRET = os.getenv("CLOUDFLARE_TURNSTILE_SECRET", "")
TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str, remote_ip: str = "") -> bool:
    if not TURNSTILE_SECRET:
        return True
    if not token:
        return False
    try:
        payload = {"secret": TURNSTILE_SECRET, "response": token}
        if remote_ip:
            payload["remoteip"] = remote_ip
        async with httpx.AsyncClient() as client:
            r = await client.post(TURNSTILE_URL, data=payload, timeout=5)
            data = r.json()
            if not data.get("success"):
                logger.warning("Turnstile rejected: %s", data.get("error-codes"))
            return data.get("success", False)
    except Exception as e:
        logger.error("Turnstile verification error: %s", e)
        return False
```

**Fail closed**: if the Cloudflare call fails or times out, the request is rejected.

**No secret = skip**: when `CLOUDFLARE_TURNSTILE_SECRET` is empty, verification is skipped.

---

### Update Request Models

**`app/models.py`:**
```python
class CrawlRequest(BaseModel):
    url: str
    cf_turnstile_response: str | None = None
```

**`app/routers/waitlist.py`:**
```python
class WaitlistStartRequest(BaseModel):
    name: str
    email: str
    website: str
    phone: str | None = None
    cf_turnstile_response: str | None = None
```

---

### Add Verification to Endpoints

**`POST /api/crawl`:**
```python
from app.services.turnstile import verify_turnstile

@router.post("/crawl", response_model=CrawlResponse)
async def start_crawl(request: Request, body: CrawlRequest, background_tasks: BackgroundTasks):
    client_ip = request.client.host if request.client else ""
    if not await verify_turnstile(body.cf_turnstile_response or "", client_ip):
        raise HTTPException(status_code=403, detail="Turnstile verification failed")
    # ... existing logic
```

**`POST /api/waitlist/start`:**
```python
@router.post("/waitlist/start")
async def waitlist_start(request: Request, body: WaitlistStartRequest):
    client_ip = request.client.host if request.client else ""
    if not await verify_turnstile(body.cf_turnstile_response or "", client_ip):
        raise HTTPException(status_code=403, detail="Turnstile verification failed")
    # ... existing logic
```

---

## Implementation Checklist

### Cloudflare setup
- [ ] Create Turnstile widget at dash.cloudflare.com
- [ ] Set domain to `getcontextus.dev`
- [ ] Copy site key and secret key
- [ ] Add `CLOUDFLARE_TURNSTILE_SECRET` to Render environment variables
- [ ] Update site key in both HTML files

### Backend
- [x] Create `app/services/turnstile.py`
- [x] Add `cf_turnstile_response` field to `CrawlRequest` model
- [x] Add Turnstile verification to `POST /api/crawl`
- [x] Add `cf_turnstile_response` field to `WaitlistStartRequest`
- [x] Add Turnstile verification to `POST /api/waitlist/start`
- [x] Add `CLOUDFLARE_TURNSTILE_SECRET` to `.env.example`

### Frontend — `/try/index.html`
- [x] Add Turnstile script tag in `<head>`
- [x] Add invisible widget div
- [x] Add `cfToken`, `submitPending`, `onTurnstileSuccess`
- [x] Modify `submitUrl()` to handle token
- [x] Handle 403 response

### Frontend — `/join/index.html`
- [x] Add Turnstile script tag in `<head>`
- [x] Add invisible widget div
- [x] Add `cfToken`, `submitPending`, `onTurnstileSuccess`
- [x] Modify `submitForm()` to handle token
- [x] Handle 403 response

---

## Token lifecycle

Turnstile tokens are **single-use and expire after ~5 minutes**. After each API call (success or failure), reset the widget:

```js
cfToken = '';
turnstile.reset('#cf-turnstile');
```

---

## Testing

1. With empty `CLOUDFLARE_TURNSTILE_SECRET` — verification skipped (local dev)
2. With test keys (`1x00...AA` / `1x00...AA`) — always passes
3. With `data-sitekey="2x00000000000000000000AB"` — always blocks, test error UI
4. Real keys — test on staging before go-live
