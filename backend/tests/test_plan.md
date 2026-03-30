# Backend API Test Plan

## Overview

This document outlines the testing strategy for the contextus backend API. The goal is to ensure all endpoints work correctly, handle edge cases, and maintain data integrity.

### Testing Approach

| Type | Scope | Speed | Dependencies |
|------|-------|-------|--------------|
| **Unit Tests** | Individual service functions | Fast | Mocked |
| **Integration Tests** | API endpoints with FastAPI TestClient | Medium | Mock Redis, Mock LLM |
| **E2E Tests** | Complete user flows | Slower | Mock LLM, real Redis (optional) |

### LLM Mocking Strategy

All LLM calls are mocked to:
- Avoid API costs during testing
- Ensure deterministic test results
- Speed up test execution

---

## Test File Structure

```
backend/tests/
├── __init__.py
├── conftest.py                    # Shared pytest fixtures
├── fixtures/
│   ├── __init__.py
│   ├── llm_responses.py           # Mock LLM response data
│   └── sample_data.py             # Test data factories
├── unit/
│   ├── __init__.py
│   ├── test_crawler.py            # Crawler service tests
│   ├── test_chunker.py            # Chunker service tests
│   ├── test_retrieval.py          # Retrieval service tests
│   ├── test_llm.py                # LLM service tests (mocked)
│   └── test_redis.py              # Redis service tests (mocked)
├── integration/
│   ├── __init__.py
│   ├── test_health.py             # Health endpoint tests
│   ├── test_crawl.py              # Crawl endpoints tests
│   ├── test_session.py            # Session endpoints tests
│   ├── test_chat.py               # Chat endpoint tests
│   └── test_brief.py              # Brief endpoint tests
└── e2e/
    ├── __init__.py
    └── test_full_flow.py          # Complete flow tests
```

---

## Test Scenarios

### 1. Health Endpoint

**File:** `tests/integration/test_health.py`

| Test Name | Method | Endpoint | Input | Expected Status | Expected Response |
|-----------|--------|----------|-------|-----------------|-------------------|
| `test_health_check` | GET | `/api/health` | - | 200 | `{"status": "ok"}` |

---

### 2. Crawl Endpoints

**File:** `tests/integration/test_crawl.py`

#### POST /api/crawl

| Test Name | Input | Expected Status | Expected Behavior |
|-----------|-------|-----------------|-------------------|
| `test_start_crawl_valid_url` | `{"url": "https://example.com"}` | 200 | Returns `job_id`, `status: crawling` |
| `test_start_crawl_invalid_protocol` | `{"url": "ftp://example.com"}` | 400 | Error: invalid URL |
| `test_start_crawl_missing_url` | `{}` | 422 | Validation error |
| `test_start_crawl_empty_url` | `{"url": ""}` | 400 | Error: invalid URL |
| `test_start_crawl_localhost` | `{"url": "http://localhost:3000"}` | 400 | Error: invalid URL (private IP) |
| `test_start_crawl_127_0_0_1` | `{"url": "http://127.0.0.1"}` | 400 | Error: invalid URL |
| `test_start_crawl_private_ip_192` | `{"url": "http://192.168.1.1"}` | 400 | Error: invalid URL |
| `test_start_crawl_private_ip_10` | `{"url": "http://10.0.0.1"}` | 400 | Error: invalid URL |
| `test_start_crawl_rate_limit_exceeded` | 4 requests same IP | 429 | Error: rate limit exceeded |
| `test_start_crawl_creates_kb_in_redis` | Valid URL | 200 | KB saved with `status: crawling` |

#### GET /api/crawl/{job_id}

| Test Name | Input | Expected Status | Expected Response |
|-----------|-------|-----------------|-------------------|
| `test_get_crawl_status_not_found` | Invalid `job_id` | 404 | Error: job not found |
| `test_get_crawl_status_crawling` | Job just created | 200 | `status: crawling`, `progress: "..."` |
| `test_get_crawl_status_complete` | Job finished | 200 | `status: complete`, `company_profile`, `chunks` |
| `test_get_crawl_status_failed` | Job failed | 200 | `status: failed`, `progress: error msg` |
| `test_get_crawl_status_returns_full_kb` | Complete job | 200 | Full `KnowledgeBase` object |

#### POST /api/crawl/{job_id}/enrich

| Test Name | Input | Expected Status | Expected Behavior |
|-----------|-------|-----------------|-------------------|
| `test_enrich_valid` | `{"answers": {"services": "We sell widgets"}}` | 200 | Returns updated `CompanyProfile` |
| `test_enrich_not_found` | Invalid `job_id` | 404 | Error: job not found |
| `test_enrich_job_not_complete` | Job still crawling | 400 | Error: job not complete |
| `test_enrich_empty_answers` | `{"answers": {}}` | 200 | No changes to profile |
| `test_enrich_adds_chunks` | Valid answers | 200 | New chunks added with source `interview:` |
| `test_enrich_updates_quality_tier` | Thin → enriched | 200 | Quality tier may improve |

---

### 3. Session Endpoints

**File:** `tests/integration/test_session.py`

#### POST /api/session

| Test Name | Input | Expected Status | Expected Behavior |
|-----------|-------|-----------------|-------------------|
| `test_create_session_valid` | Valid `knowledge_base_id` | 200 | Returns `session_id` |
| `test_create_session_kb_not_found` | Invalid KB ID | 404 | Error: knowledge base not found |
| `test_create_session_kb_not_ready` | KB status = `crawling` | 400 | Error: knowledge base not ready |
| `test_create_session_kb_failed` | KB status = `failed` | 400 | Error: knowledge base not ready |
| `test_create_session_saves_to_redis` | Valid KB | 200 | Session saved with TTL |

#### GET /api/session/{session_id}

| Test Name | Input | Expected Status | Expected Response |
|-----------|-------|-----------------|-------------------|
| `test_get_session_valid` | Valid `session_id` | 200 | Session object with messages |
| `test_get_session_not_found` | Invalid `session_id` | 404 | Error: session not found |
| `test_get_session_with_messages` | Session with chat history | 200 | Includes message array |
| `test_get_session_with_contact` | Contact captured | 200 | `contact_captured: true`, `contact_value` |

---

### 4. Chat Endpoint

**File:** `tests/integration/test_chat.py`

#### POST /api/chat/{session_id}

| Test Name | Input | Expected Status | Expected Behavior |
|-----------|-------|-----------------|-------------------|
| `test_chat_valid_message` | `{"message": "What services?"}` | 200 | SSE stream with tokens |
| `test_chat_session_not_found` | Invalid `session_id` | 404 | Error: session not found |
| `test_chat_kb_not_found` | Session with invalid KB | 404 | Error: knowledge base not found |
| `test_chat_kb_no_profile` | KB without profile | 400 | Error: no company profile |
| `test_chat_message_limit_exceeded` | 61st message (30 turns) | 429 | Error: message limit reached |
| `test_chat_message_limit_ok` | 60th message | 200 | Still works |

**SSE Format Tests:**

| Test Name | Expected Behavior |
|-----------|-------------------|
| `test_chat_sse_content_type` | Response `content-type: text/event-stream` |
| `test_chat_sse_token_format` | Chunks are `data: {"token": "..."}\n\n` |
| `test_chat_sse_done_format` | Final chunk is `data: {"done": true, "full_text": "..."}\n\n` |
| `test_chat_sse_tokens_are_valid_json` | Each `data:` line is valid JSON |
| `test_chat_sse_full_text_matches_tokens` | Concatenated tokens = full_text |

**Contact Detection Tests:**

| Test Name | Input | Expected |
|-----------|-------|----------|
| `test_chat_detect_email` | `"Email me at test@example.com"` | `contact_captured: true` |
| `test_chat_detect_email_multiple` | `"test@a.com and test@b.com"` | First email captured |
| `test_chat_detect_phone_indo_08` | `"Call 08123456789"` | `contact_captured: true` |
| `test_chat_detect_phone_indo_62` | `"Call +62812345678"` | `contact_captured: true` |
| `test_chat_detect_whatsapp_wa_me` | `"wa.me/62812345678"` | `contact_captured: true` |
| `test_chat_detect_whatsapp_url` | `"whatsapp.com/send?phone=..."` | `contact_captured: true` |
| `test_chat_no_contact` | `"What are your hours?"` | `contact_captured: false` |

**Session Persistence Tests:**

| Test Name | Expected Behavior |
|-----------|-------------------|
| `test_chat_saves_user_message` | User message in session after stream |
| `test_chat_saves_assistant_message` | Assistant message in session after stream |
| `test_chat_preserves_message_order` | Messages in correct order |
| `test_chat_updates_session_ttl` | Session TTL refreshed after chat |

---

### 5. Brief Endpoint

**File:** `tests/integration/test_brief.py`

#### POST /api/brief/{session_id}

| Test Name | Input | Expected Status | Expected Behavior |
|-----------|-------|-----------------|-------------------|
| `test_brief_valid` | Session with 3+ messages | 200 | Returns `LeadBrief` object |
| `test_brief_minimum_messages` | Session with exactly 2 messages | 200 | Returns `LeadBrief` |
| `test_brief_insufficient_messages` | Session with 1 message | 400 | Error: need 2+ messages |
| `test_brief_empty_session` | Session with 0 messages | 400 | Error: need 2+ messages |
| `test_brief_session_not_found` | Invalid `session_id` | 404 | Error: session not found |
| `test_brief_kb_not_found` | Session with invalid KB | 404 | Error: knowledge base not found |

**LeadBrief Structure Tests:**

| Test Name | Expected |
|-----------|----------|
| `test_brief_has_required_fields` | `who`, `need`, `signals`, `open_questions`, `suggested_approach`, `quality_score` |
| `test_brief_quality_score_valid` | `quality_score` is `high`, `medium`, or `low` |
| `test_brief_includes_session_id` | `session_id` matches request |
| `test_brief_includes_contact` | If contact was captured, it's in brief |

---

## Unit Tests

### test_crawler.py

| Test Name | Input | Expected Output |
|-----------|-------|-----------------|
| `test_validate_url_https` | `"https://example.com"` | `True` |
| `test_validate_url_http` | `"http://example.com"` | `True` |
| `test_validate_url_no_protocol` | `"example.com"` | `False` |
| `test_validate_url_ftp` | `"ftp://example.com"` | `False` |
| `test_validate_url_localhost` | `"http://localhost:3000"` | `False` |
| `test_validate_url_127_0_0_1` | `"http://127.0.0.1"` | `False` |
| `test_validate_url_192_168` | `"http://192.168.1.1"` | `False` |
| `test_validate_url_10_x` | `"http://10.0.0.1"` | `False` |
| `test_validate_url_172_x` | `"http://172.16.0.1"` | `False` |
| `test_is_valid_url_same_domain` | Link to same domain | `True` |
| `test_is_valid_url_different_domain` | Link to different domain | `False` |
| `test_is_valid_url_pdf` | `.pdf` link | `False` |
| `test_is_valid_url_jpg` | `.jpg` link | `False` |
| `test_is_valid_url_anchor` | `#section` | `False` |
| `test_is_valid_url_mailto` | `mailto:test@test.com` | `False` |
| `test_is_valid_url_javascript` | `javascript:void(0)` | `False` |

### test_chunker.py

| Test Name | Input | Expected Output |
|-----------|-------|-----------------|
| `test_chunk_short_paragraph` | < 500 chars, 20+ words | 1 chunk |
| `test_chunk_long_paragraph` | 1000 chars | 2+ chunks with overlap |
| `test_chunk_filter_short` | < 20 words | 0 chunks |
| `test_chunk_exactly_20_words` | Exactly 20 words | 1 chunk |
| `test_chunk_multiple_paragraphs` | 3 paragraphs | 3+ chunks |
| `test_chunk_empty_text` | Empty string | 0 chunks |
| `test_chunk_whitespace_only` | Only whitespace | 0 chunks |
| `test_chunk_preserves_source` | Source URL | Source in chunk |
| `test_chunk_generates_unique_ids` | Multiple chunks | Each has unique ID |
| `test_chunk_word_count_accurate` | Any text | `word_count` matches |
| `test_chunk_pages_empty` | Empty list | 0 chunks |
| `test_chunk_pages_multiple` | 3 pages | Combined chunks from all |

### test_retrieval.py

| Test Name | Input | Expected Output |
|-----------|-------|-----------------|
| `test_tokenize_basic` | `"hello world"` | `{'hello', 'world'}` |
| `test_tokenize_case_insensitive` | `"Hello WORLD"` | `{'hello', 'world'}` |
| `test_tokenize_removes_punctuation` | `"hello, world!"` | `{'hello', 'world'}` |
| `test_tokenize_removes_stopwords` | `"the quick brown fox"` | No 'the' |
| `test_tokenize_short_words` | `"a an is"` | Empty set |
| `test_retrieve_chunks_exact_match` | Query word in chunk | Chunk scored high |
| `test_retrieve_chunks_partial_match` | Some words match | Lower score |
| `test_retrieve_chunks_no_match` | No words match | Score = 0 |
| `test_retrieve_chunks_empty_query` | Empty query | First K chunks |
| `test_retrieve_chunks_empty_list` | Empty chunks | Empty list |
| `test_retrieve_chunks_top_k` | 10 chunks, top_k=3 | 3 chunks |
| `test_retrieve_chunks_ordering` | Varying relevance | Ordered by score desc |

### test_llm.py (Mocked)

| Test Name | Mock Input | Expected Output |
|-----------|------------|-----------------|
| `test_generate_company_profile` | Mock JSON response | `CompanyProfile` object |
| `test_generate_company_profile_missing_fields` | Partial JSON | Default values |
| `test_stream_chat_response` | Mock token stream | Iterator of tokens |
| `test_stream_chat_response_empty` | Empty stream | Empty iterator |
| `test_generate_lead_brief` | Mock JSON response | `LeadBrief` object |
| `test_generate_lead_brief_quality_scores` | Various scores | Valid score values |
| `test_assess_quality_tier_rich` | 2000+ words, 3+ sources | `"rich"` |
| `test_assess_quality_tier_thin` | 500-1999 words | `"thin"` |
| `test_assess_quality_tier_empty` | < 500 words | `"empty"` |
| `test_build_chat_system_prompt` | Profile + chunks | Formatted prompt |

### test_redis.py (Mocked)

| Test Name | Mock Behavior | Expected Output |
|-----------|---------------|-----------------|
| `test_save_knowledge_base` | Redis.set called | Called with JSON + TTL |
| `test_get_knowledge_base_found` | Redis.get returns JSON | `KnowledgeBase` object |
| `test_get_knowledge_base_not_found` | Redis.get returns None | `None` |
| `test_save_session` | Redis.set called | Called with JSON + TTL |
| `test_get_session_found` | Redis.get returns JSON | `Session` object |
| `test_get_session_not_found` | Redis.get returns None | `None` |
| `test_check_rate_limit_first_request` | No existing key | `True`, key created |
| `test_check_rate_limit_under_limit` | Count < max | `True`, count++ |
| `test_check_rate_limit_at_limit` | Count >= max | `False` |
| `test_check_rate_limit_expired` | Key expired | `True`, new key |
| `test_kb_key_format` | `job_id="abc"` | `"kb:abc"` |
| `test_session_key_format` | `session_id="xyz"` | `"session:xyz"` |
| `test_rate_key_format` | `ip="1.2.3.4", action="crawl"` | `"rate:1.2.3.4:crawl"` |

---

## E2E Tests

### test_full_flow.py

| Test Name | Flow | Expected Outcome |
|-----------|------|------------------|
| `test_happy_path` | 1. POST crawl → 2. Poll until complete → 3. POST session → 4. POST chat × 3 → 5. POST brief | Full flow completes successfully |
| `test_happy_path_with_contact` | Same + user shares email | `contact_captured: true` in brief |
| `test_thin_content_enrichment` | 1. Crawl thin site → 2. Enrich → 3. Session → 4. Chat | Enrichment improves profile |
| `test_rate_limit_flow` | 4 concurrent crawls same IP | 3 succeed, 1 gets 429 |
| `test_session_expiry` | Create session, wait, try to use | 404 after expiry |
| `test_multiple_sessions_same_kb` | 2 sessions from 1 KB | Both work independently |
| `test_concurrent_chats_same_session` | 2 concurrent messages | Both processed (or one fails gracefully) |

---

## Fixtures

### conftest.py

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

# Fixtures:
# - test_client: TestClient with mocked dependencies
# - mock_redis: MagicMock for Redis operations
# - mock_llm_client: MagicMock for OpenAI client
# - sample_knowledge_base: KnowledgeBase factory
# - sample_session: Session factory
# - sample_chunks: List[Chunk] factory
# - sample_company_profile: CompanyProfile factory
# - sample_lead_brief: LeadBrief factory
```

### fixtures/llm_responses.py

```python
# Mock LLM responses for consistent testing

COMPANY_PROFILE_RESPONSE = {
    "name": "Test Company",
    "industry": "Technology",
    "services": ["Web Development", "Mobile Apps"],
    "location": "Jakarta, Indonesia",
    "contact": "hello@testcompany.com",
    "summary": "A test company for testing purposes.",
    "gaps": ["pricing information", "team bios"]
}

CHAT_STREAM_TOKENS = [
    "Hello", "!", " How", " can", " I", " help", " you", " today", "?"
]

LEAD_BRIEF_RESPONSE = {
    "who": "A potential customer interested in web development",
    "need": "Website development for their business",
    "signals": "Asked about pricing timeline",
    "open_questions": "What is their budget?",
    "suggested_approach": "Follow up with pricing sheet",
    "quality_score": "high"
}
```

### fixtures/sample_data.py

```python
# Factory functions for test data

def create_sample_chunk(text="Sample content", source="https://example.com"):
    ...

def create_sample_company_profile():
    ...

def create_sample_knowledge_base(status="complete"):
    ...

def create_sample_session(message_count=0, has_contact=False):
    ...

def create_sample_lead_brief():
    ...
```

---

## Running Tests

### Commands

```bash
# Run all tests
pytest

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run specific test file
pytest tests/integration/test_crawl.py

# Run specific test
pytest tests/integration/test_crawl.py::test_start_crawl_valid_url

# Verbose output
pytest -v

# With coverage report
pytest --cov=app --cov-report=html

# With coverage, only missing lines
pytest --cov=app --cov-report=term-missing

# Parallel execution (requires pytest-xdist)
pytest -n auto

# Stop on first failure
pytest -x

# Show print statements
pytest -s
```

### Requirements

Add to `requirements.txt` or `requirements-dev.txt`:

```
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=4.0.0
httpx>=0.27.0  # Already in main requirements
```

---

## Coverage Goals

| Category | Target Coverage |
|----------|-----------------|
| Services | 90%+ |
| Routers | 85%+ |
| Models | 100% (trivial) |
| Overall | 85%+ |

---

## CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      - name: Run tests
        run: |
          cd backend
          pytest --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

---

## Test Data Cleanup

Tests should not leave data in Redis. Use:
- Unique key prefixes for test data
- Short TTLs for test data
- Cleanup in fixture teardown

---

## Known Limitations

1. **LLM responses are mocked** - Real LLM behavior may differ
2. **No real network calls** - Crawler tests mock httpx responses
3. **No real Redis in CI** - All Redis calls mocked
4. **No WebSocket tests** - Using SSE only

---

## Future Improvements

1. Add property-based testing with `hypothesis`
2. Add load testing with `locust`
3. Add contract testing for API versioning
4. Add mutation testing with `mutmut`
