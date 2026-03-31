# Backend API Test Plan

## Overview

This document tracks the testing strategy and current status for the contextus backend API.

### Three-Tier Architecture (Implemented)

| Tier | Scope | Speed | Dependencies | Status |
|------|-------|-------|--------------|--------|
| **Integration** | API endpoints via FastAPI TestClient | ~0.7s (51 tests) | Mock Redis, Mock LLM | ✅ All passing |
| **E2E Server** | Real HTTP to subprocess uvicorn | ~1.9s (14 tests) | Real server, no credentials | ✅ All passing |
| **E2E Pipeline** | Full crawl → chat → brief with live services | ~27s (13 tests) | Real Redis + OpenRouter + live web | ✅ All passing |

### What's NOT yet written

- `tests/unit/` — all files are empty placeholders. Unit tests for individual service functions (crawler, chunker, retrieval, llm, redis) have been planned but not implemented.

---

## Current Test File Structure

```
backend/tests/
├── __init__.py
├── conftest.py                    # Integration test fixtures (mocked Redis + LLM)
├── fixtures/
│   ├── __init__.py
│   ├── llm_responses.py           # Mock LLM response data
│   └── sample_data.py             # Test data factories
├── unit/                          # ⚠️ EMPTY — not yet implemented
│   ├── __init__.py
│   ├── test_crawler.py
│   ├── test_chunker.py
│   ├── test_retrieval.py
│   ├── test_llm.py
│   └── test_redis.py
├── integration/                   # ✅ 51 tests passing
│   ├── __init__.py
│   ├── test_health.py
│   ├── test_crawl.py
│   ├── test_session.py
│   ├── test_chat.py
│   └── test_brief.py
└── e2e/                           # ✅ 27 tests passing (14 server + 13 pipeline)
    ├── __init__.py
    ├── conftest.py                # Real server fixture + rate limit reset fixture
    ├── test_server.py             # 14 tests — real HTTP, no credentials needed
    └── test_real_pipeline.py      # 13 tests — live Redis + OpenRouter + web crawl
```

---

## Running Tests

### Daily development (fast, no credentials)

```bash
cd backend

# Integration tests only (~0.7s)
pytest tests/integration/ -v

# Integration + E2E server tests (~2s)
pytest tests/integration/ tests/e2e/test_server.py -v
```

### Full validation (requires credentials in .env)

```bash
# Real pipeline (costs money, ~27s, requires OPENROUTER_API_KEY + UPSTASH_REDIS_REST_TOKEN)
pytest tests/e2e/test_real_pipeline.py -v -s

# Everything
pytest -v
```

### Useful flags

```bash
pytest -x          # Stop on first failure
pytest -s          # Show print output (useful for real pipeline tests)
pytest -k "crawl"  # Run only tests matching "crawl"
pytest --tb=short  # Shorter tracebacks
```

---

## E2E Server Tests (`tests/e2e/test_server.py`) — 14 tests

Tests that hit a real uvicorn server over HTTP. No credentials needed. Server is spun up as a subprocess on port 8001, torn down after the session.

| Test | Validates |
|------|-----------|
| `test_health_returns_ok` | GET /api/health → 200 `{"status": "ok"}` |
| `test_health_content_type` | Response is `application/json` |
| `test_health_response_time` | Responds in < 500ms |
| `test_crawl_missing_url` | POST /api/crawl `{}` → 422 |
| `test_crawl_invalid_protocol` | `ftp://...` → 400 |
| `test_crawl_localhost` | `http://localhost` → 400 |
| `test_crawl_private_ip_192` | `http://192.168.1.1` → 400 |
| `test_crawl_private_ip_10` | `http://10.0.0.1` → 400 |
| `test_crawl_unknown_job` | GET /api/crawl/nonexistent → 404 |
| `test_session_missing_kb_id` | POST /api/session `{}` → 422 |
| `test_session_invalid_kb_id` | POST /api/session unknown KB → 404 |
| `test_chat_unknown_session` | POST /api/chat/nonexistent → 404 |
| `test_brief_unknown_session` | POST /api/brief/nonexistent → 404 |
| `test_crawl_valid_url_starts_job` | Valid URL → 200 with `job_id` and `status: crawling` |

---

## E2E Real Pipeline Tests (`tests/e2e/test_real_pipeline.py`) — 13 tests

Full end-to-end tests with live services. Auto-skipped if `OPENROUTER_API_KEY` or `UPSTASH_REDIS_REST_TOKEN` not in `.env`. Uses `https://project-b0yme.vercel.app` (the contextus landing page) as the test URL.

Module-scoped fixtures chain: `crawled_kb` → `active_session` → `session_with_messages`

### TestCrawlPipeline

| Test | Validates |
|------|-----------|
| `test_crawl_completes` | Job reaches `status: complete` within 60s |
| `test_crawl_finds_pages` | At least 1 page crawled |
| `test_crawl_produces_chunks` | Content chunked successfully |
| `test_crawl_sets_quality_tier` | Quality tier is `rich`, `thin`, or `empty` |
| `test_crawl_generates_company_profile` | Profile has `name`, `summary`, `services[]`, `gaps[]` |

### TestSessionPipeline

| Test | Validates |
|------|-----------|
| `test_session_created` | Session ID returned |
| `test_session_is_retrievable` | GET /api/session/:id returns session |
| `test_session_starts_empty` | Fresh session has no messages |

### TestChatPipeline

| Test | Validates |
|------|-----------|
| `test_chat_streams_tokens` | SSE stream delivers tokens, content-type is `text/event-stream` |
| `test_chat_message_saved_to_session` | After chat, session contains user + assistant messages |

### TestBriefPipeline

| Test | Validates |
|------|-----------|
| `test_brief_generates` | POST /api/brief returns 200 |
| `test_brief_has_required_fields` | All 6 fields present and non-empty |
| `test_brief_quality_score_is_valid` | Score is `high`, `medium`, or `low` |

---

## Integration Tests (`tests/integration/`) — 51 tests

FastAPI `TestClient` with patched Redis and LLM. Fast, deterministic, no external services.

### test_health.py (1 test)
- `test_health_check` — GET /api/health → 200 `{"status": "ok"}`

### test_crawl.py (~15 tests)
- Valid crawl start, missing URL (422), invalid protocols (400), localhost/private IPs (400)
- Rate limit: 4th request from same IP → 429
- GET crawl status: known job, unknown job (404), crawling/complete/failed states

### test_session.py (~8 tests)
- Create session: valid KB, KB not found (404), KB not complete (400)
- Get session: valid, not found (404)

### test_chat.py (~15 tests)
- SSE stream format: content-type, token format, done event
- Session not found (404), KB not found (404), no company profile (400)
- Message limit exceeded (429), contact detection (email, phone, WhatsApp)
- Message persistence after stream

### test_brief.py (~12 tests)
- Valid brief generation, insufficient messages (400), session/KB not found (404)
- Required fields present, quality score valid, session_id matches

---

## Bugs Discovered and Fixed Through Testing

| Bug | Found By | Fix |
|-----|----------|-----|
| **Rate limit consumed by invalid URLs** | E2E server tests (ftp://, localhost, 192.168.* all hit rate limiter before URL validation) | In `crawl.py`: moved `validate_url()` check BEFORE `check_rate_limit()` |
| **macOS/Miniconda SSL: `CERTIFICATE_VERIFY_FAILED`** | E2E pipeline tests (HTTPS crawl fails on Miniconda Python) | Added `truststore` package + `truststore.inject_into_ssl()` at top of `main.py` |
| **LLM returns JSON wrapped in prose** | E2E pipeline tests (`json.loads()` fails on "Here is the JSON: {...}") | Added `extract_json()` helper with regex fallback: `re.search(r'\{.*\}', text, re.DOTALL)` |
| **`example.com` produces 0 chunks** | E2E pipeline tests (40 words total, all paragraphs < 20-word threshold) | Changed `TEST_URL` from `example.com` to `project-b0yme.vercel.app` |
| **Brief endpoint `ReadTimeout`** | E2E pipeline tests (LLM call takes 10-20s, httpx default timeout is 5s) | Added `timeout=30` to all brief test requests |
| **Fixture scope mismatch** | E2E pipeline tests (`crawled_kb` module-scope uses `clear_crawl_rate_limit` function-scope) | Changed `clear_crawl_rate_limit` to `scope="module"` in `e2e/conftest.py` |

---

## Unit Tests (Planned, Not Yet Implemented)

`tests/unit/` files exist but are empty. The tests below are the original plan — implement when needed.

### test_crawler.py
- `validate_url()`: https ✓, http ✓, ftp ✗, no-protocol ✗, localhost ✗, 127.0.0.1 ✗, 192.168.* ✗, 10.* ✗, 172.16.* ✗
- `is_valid_link()`: same-domain ✓, different-domain ✗, .pdf ✗, .jpg ✗, `#anchor` ✗, `mailto:` ✗

### test_chunker.py
- `chunk_text()`: short paragraph (1 chunk), long paragraph (2+ chunks with overlap), < 20 words filtered, empty text → 0 chunks
- `chunk_pages()`: empty list, multiple pages, unique IDs, accurate word counts

### test_retrieval.py
- `retrieve_chunks()`: exact match ranked first, top_k enforced, empty query, empty chunks list, ordering by score descending

### test_llm.py (mocked)
- `assess_quality_tier()`: rich (2000+ words, 3+ sources), thin (500-1999 words), empty (< 500 words)
- `extract_json()`: plain JSON, prose-wrapped JSON, invalid JSON raises
- `build_chat_system_prompt()`: contains company name, services, knowledge chunks

### test_redis.py (mocked)
- `save_knowledge_base()` / `get_knowledge_base()`: round-trip serialization, None when missing
- `save_session()` / `get_session()`: same
- `check_rate_limit()`: first request → True, under limit → True, at limit → False

---

## What's Next

1. **Widget integration** — Replace mock response engine in `widget/` with real fetch calls to backend
2. **Landing page URL-input flow** — Phase 5 "proof of magic" demo
3. **Unit tests** — Fill in `tests/unit/` when isolating service-level regressions becomes important
4. **WhatsApp/email delivery** — Phase 4, after demo validates
