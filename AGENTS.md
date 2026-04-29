# AGENTS.md — Contextus Agent Coding Guide

This file provides coding conventions and commands for agents operating on the contextus codebase.

---

## Project Structure

```
contextus/
├── backend/           # Python FastAPI backend (app/)
│   ├── app/
│   │   ├── routers/   # API route handlers (crawl, chat, session, etc.)
│   │   ├── services/  # Business logic (crawler, llm, redis, etc.)
│   │   └── main.py    # FastAPI app entry
│   └── tests/
│       ├── unit/      # Unit tests (no external deps)
│       ├── integration/   # Integration tests (TestClient)
│       └── e2e/      # E2E tests (real HTTP server)
├── widget/            # Vanilla JS widget frontend
│   └── tests/          # Playwright tests
├── docs/              # Design docs, planning docs
├── site/              # Landing page
└── package.json      # Frontend build/test commands
```

---

## Build/Lint/Test Commands

### Frontend (Widget)

```bash
# Run all widget tests
npm test

# Run specific Playwright test file
npx playwright test widget/tests/widget.spec.ts

# Run with UI (debugging)
npx playwright test --ui

# Run single test
npx playwright test widget/tests/widget.spec.ts -g "test name"
```

### Backend (Python)

```bash
cd backend

# Run all tests
pytest -v

# Run specific test category
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/test_server.py -v

# Run single test (most common pattern)
pytest tests/integration/test_crawl.py::test_start_crawl_valid_url -v
pytest tests/unit/test_third_party_resilience.py::TestRedisResilience::test_get_knowledge_base_redis_down_returns_none -v

# Run with verbose output
pytest tests/integration/test_crawl.py -v --tb=short

# Run E2E server tests (starts real uvicorn)
pytest tests/e2e/test_server.py -v
```

### Development Server

```bash
# Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Frontend (widget static files)
npx serve . -p 3000
```

---

## Code Style Guidelines

### Python (Backend)

**Imports** — Grouped in this order, separated by blank lines:

```python
# Standard library
import os
import time
from contextlib import asynccontextmanager

# Third-party packages (alphabetical)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pytest

# Local application
from app.models import KnowledgeBase, CompanyProfile
from app.services.redis import save_knowledge_base
```

**Type Hints** — Use Python 3.10+ union syntax:

```python
# Prefer this:
name: str | None = None
status: Literal["crawling", "complete", "failed"] | None = None

# Over this:
from typing import Optional, Union
name: Optional[str] = None
```

**Async Functions** — Always use `async def` for route handlers and I/O-bound operations:

```python
@router.get("/crawl/{job_id}")
async def get_crawl_status(job_id: str):
    kb = await get_knowledge_base(job_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Job not found")
    return kb
```

**Error Handling** — Use HTTPException for API errors; catch expected failures gracefully:

```python
# Route level — return proper HTTP status codes
if not kb:
    raise HTTPException(status_code=404, detail="Job not found")

# Service level — handle known failure modes
try:
    await save_knowledge_base(job_id, kb)
except Exception as e:
    logger.error(f"Failed to save KB: {e}")
    # Degrade gracefully, don't crash
```

**Naming Conventions:**

- Routes/routers: `snake_case` (e.g., `crawl.py`, `session.py`)
- Models (Pydantic): `PascalCase` (e.g., `CompanyProfile`, `KnowledgeBase`)
- Functions/variables: `snake_case` (e.g., `get_knowledge_base`, `job_id`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEMO_URL`, `E2E_PORT`)

**FastAPI Patterns:**

```python
# Define response model for documentation
@router.post("/crawl", response_model=CrawlResponse)
async def start_crawl(request: Request, body: CrawlRequest, background_tasks: BackgroundTasks):
    ...

# Use tags for OpenAPI grouping
router = APIRouter(tags=["crawl"])

# Request models in app/models.py — not inline
class CrawlRequest(BaseModel):
    url: str
    cf_turnstile_response: str | None = None
```

**Testing Patterns:**

```python
# Integration test with TestClient
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_start_crawl_valid_url():
    response = client.post("/api/crawl", json={"url": "https://example.com"})
    assert response.status_code == 200

# Unit test with mocks
from unittest.mock import patch, AsyncMock

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_rate_limit_exceeded(mock_rate_limit):
    mock_rate_limit.return_value = False
    response = client.post("/api/crawl", json={"url": "https://example.com"})
    assert response.status_code == 429

# Async test with pytest-asyncio
import pytest

@pytest.mark.asyncio
async def test_get_knowledge_base_redis_down_returns_none():
    with patch("app.services.redis.redis.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Upstash: unauthorized")
        result = await get_knowledge_base("job_abc")
        assert result is None
```

---

### JavaScript/TypeScript (Widget)

**Style** — Follow existing patterns in `widget/tests/`:

- Use Playwright for E2E tests
- Mock API responses with helper functions
- Test both floating and embedded widget modes

---

## Key Architecture Patterns

### Knowledge Base Flow

```
POST /api/crawl → job_id + "crawling"
GET  /api/crawl/{job_id} → status + progress
POST /api/crawl/{job_id}/enrich → updated profile
```

### Session Flow

```
POST /api/session → session_id + pills
WS /api/chat/{session_id} → streaming messages
```

### Resilience Patterns

- **Redis failure**: Fall back gracefully, return None, don't 500
- **Neon failure**: Silently skip database, use Redis only
- **Firecrawl failure**: Fall back to httpx scraping
- **LLM failure**: Use partial/default profile, never crash

---

## Important Files

| File | Purpose |
|------|---------|
| `backend/app/models.py` | Pydantic request/response models |
| `backend/app/main.py` | FastAPI app setup, router registration |
| `backend/app/routers/crawl.py` | Crawl API endpoints |
| `backend/app/services/llm.py` | LLM integration, profile generation |
| `CLAUDE-CODE-BRIEF.md` | Product context and requirements |
| `docs/contextus-widget-design-guideline.html` | Widget design spec |

---

## Environment Variables

Backend uses `.env` file (see `.env.example`):

```
PORT=8000
FIRECRAWL_API_KEY=...
OPENROUTER_API_KEY=...
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
DATABASE_URL=...  # Neon PostgreSQL
ALLOWED_ORIGINS=...
```

---

## Common Tasks

### Run a single backend integration test:

```bash
cd backend
pytest tests/integration/test_crawl.py::test_start_crawl_valid_url -v
```

### Run a single widget Playwright test:

```bash
npx playwright test widget/tests/widget.spec.ts -g "widget appears"
```

### Add a new API endpoint:

1. Create router in `backend/app/routers/<name>.py`
2. Import and register in `backend/app/main.py`:
   ```python
   from app.routers import crawl, session, chat, <name>
   app.include_router(<name>.router, prefix="/api")
   ```
3. Add request/response models in `backend/app/models.py`

### Add a new test:

- **Integration**: Add to `backend/tests/integration/test_<feature>.py`
- **Unit**: Add to `backend/tests/unit/test_<module>.py`
- **E2E**: Add to `backend/tests/e2e/test_<feature>.py`

---

Generated for agentic coding. Update this file as conventions evolve.