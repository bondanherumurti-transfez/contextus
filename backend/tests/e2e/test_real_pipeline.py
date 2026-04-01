"""
Real pipeline tests — live server + real Redis + real LLM.

These hit actual Upstash Redis and OpenRouter (costs money, ~15-30s).
Skipped automatically if credentials are not present in .env.

Run with:  pytest tests/e2e/test_real_pipeline.py -v -s
"""

import os
import time
import json
import pytest
import httpx
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

# Skip entire module if real credentials are absent
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

if not OPENROUTER_KEY or not REDIS_TOKEN:
    pytest.skip(
        "Real credentials not set — needs OPENROUTER_API_KEY + UPSTASH_REDIS_REST_TOKEN in .env",
        allow_module_level=True,
    )

# The contextus landing page — real content, controlled by us, guaranteed to produce chunks
TEST_URL = "https://project-b0yme.vercel.app"
POLL_TIMEOUT = 60   # seconds to wait for crawl to complete
POLL_INTERVAL = 2   # seconds between polls


def poll_until_complete(base_url: str, job_id: str) -> dict:
    """Poll GET /api/crawl/{job_id} until status is complete or failed."""
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        r = httpx.get(f"{base_url}/api/crawl/{job_id}")
        assert r.status_code == 200, f"Unexpected status: {r.status_code}"
        data = r.json()
        status = data["status"]
        print(f"  [{status}] {data.get('progress', '')}")
        if status == "complete":
            return data
        if status == "failed":
            pytest.fail(f"Crawl job failed: {data.get('progress')}")
        time.sleep(POLL_INTERVAL)
    pytest.fail(f"Crawl did not complete within {POLL_TIMEOUT}s")


# ---------------------------------------------------------------------------
# Fixtures — shared state across pipeline stages
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def crawled_kb(server, clear_crawl_rate_limit):
    """Submit a real crawl job and wait for it to complete. Shared across module."""
    r = httpx.post(f"{server}/api/crawl", json={"url": TEST_URL})
    assert r.status_code == 200, f"Crawl failed to start: {r.text}"
    job_id = r.json()["job_id"]
    print(f"\n  Crawl started: job_id={job_id}")

    kb = poll_until_complete(server, job_id)
    return kb


@pytest.fixture(scope="module")
def active_session(server, crawled_kb):
    """Create a chat session from the completed knowledge base."""
    kb_id = crawled_kb["job_id"]
    r = httpx.post(f"{server}/api/session", json={"knowledge_base_id": kb_id})
    assert r.status_code == 200, f"Session creation failed: {r.text}"
    return r.json()["session_id"]


@pytest.fixture(scope="module")
def session_with_messages(server, active_session):
    """Send a real chat message and collect the SSE response. Returns session_id."""
    tokens = []
    with httpx.stream(
        "POST",
        f"{server}/api/chat/{active_session}",
        json={"message": "What is this website about?"},
        timeout=30,
    ) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if "token" in payload:
                    tokens.append(payload["token"])
                if payload.get("done"):
                    break

    print(f"\n  Chat response: {''.join(tokens)[:100]}...")
    return active_session


# ---------------------------------------------------------------------------
# Tests — each stage builds on the previous fixture
# ---------------------------------------------------------------------------

class TestCrawlPipeline:
    def test_crawl_completes(self, crawled_kb):
        """Crawl job reaches 'complete' status."""
        assert crawled_kb["status"] == "complete"

    def test_crawl_finds_pages(self, crawled_kb):
        """At least one page was crawled."""
        assert crawled_kb["pages_found"] >= 1

    def test_crawl_produces_chunks(self, crawled_kb):
        """Content was extracted and chunked."""
        assert len(crawled_kb["chunks"]) >= 1

    def test_crawl_sets_quality_tier(self, crawled_kb):
        """Quality tier is assessed as rich, thin, or empty."""
        assert crawled_kb["quality_tier"] in ("rich", "thin", "empty")

    def test_crawl_generates_company_profile(self, crawled_kb):
        """LLM extracted a company profile with required fields."""
        profile = crawled_kb["company_profile"]
        assert profile is not None
        assert profile["name"]       # name was extracted
        assert profile["summary"]    # summary was written
        assert isinstance(profile["services"], list)
        assert isinstance(profile["gaps"], list)


class TestSessionPipeline:
    def test_session_created(self, active_session):
        """Session ID is returned and non-empty."""
        assert active_session
        assert len(active_session) > 0

    def test_session_is_retrievable(self, server, active_session):
        """GET /api/session/:id returns the session."""
        r = httpx.get(f"{server}/api/session/{active_session}")
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == active_session
        assert data["kb_id"]

    def test_session_starts_empty(self, server, active_session):
        """Fresh session has no messages yet."""
        r = httpx.get(f"{server}/api/session/{active_session}")
        assert r.json()["messages"] == []


class TestChatPipeline:
    def test_chat_streams_tokens(self, server, active_session):
        """Sending a message produces an SSE stream with tokens."""
        tokens = []
        with httpx.stream(
            "POST",
            f"{server}/api/chat/{active_session}",
            json={"message": "What is this website about?"},
            timeout=30,
        ) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
            for line in r.iter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    if "token" in payload:
                        tokens.append(payload["token"])
                    if payload.get("done"):
                        break

        assert len(tokens) > 0, "No tokens received from stream"
        full_response = "".join(tokens)
        assert len(full_response) > 10, "Response too short to be meaningful"

    def test_chat_message_saved_to_session(self, server, session_with_messages):
        """After chatting, session contains message history."""
        r = httpx.get(f"{server}/api/session/{session_with_messages}")
        messages = r.json()["messages"]
        assert len(messages) >= 2  # user + assistant
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles


class TestBriefPipeline:
    def test_brief_generates(self, server, session_with_messages):
        """Lead brief is generated from a real conversation."""
        r = httpx.post(f"{server}/api/brief/{session_with_messages}", timeout=30)
        assert r.status_code == 200

    def test_brief_has_required_fields(self, server, session_with_messages):
        """Generated brief contains all expected fields."""
        r = httpx.post(f"{server}/api/brief/{session_with_messages}", timeout=30)
        data = r.json()
        for field in ("who", "need", "signals", "open_questions", "suggested_approach", "quality_score"):
            assert field in data, f"Missing field: {field}"
            assert data[field], f"Empty field: {field}"

    def test_brief_quality_score_is_valid(self, server, session_with_messages):
        """Quality score is one of the expected values."""
        r = httpx.post(f"{server}/api/brief/{session_with_messages}", timeout=30)
        assert r.json()["quality_score"] in ("high", "medium", "low")
