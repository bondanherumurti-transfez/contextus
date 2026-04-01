"""
E2E tests — real uvicorn server, real HTTP via httpx.

These tests prove the server actually boots, routes are reachable,
and basic contracts hold. No mocking.

Run with:  pytest tests/e2e/ -v
"""

import time
import httpx
import pytest


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_server_is_live(server):
    """Server boots and health endpoint returns 200."""
    r = httpx.get(f"{server}/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_content_type(server):
    """Health response is JSON."""
    r = httpx.get(f"{server}/api/health")
    assert "application/json" in r.headers["content-type"]


def test_health_responds_fast(server):
    """Health check completes in under 500ms (no DB calls, just a ping)."""
    start = time.time()
    httpx.get(f"{server}/api/health")
    elapsed_ms = (time.time() - start) * 1000
    assert elapsed_ms < 500, f"Health check took {elapsed_ms:.0f}ms — too slow"


# ---------------------------------------------------------------------------
# Crawl — request validation (no Redis/LLM needed, returns 4xx fast)
# ---------------------------------------------------------------------------

def test_crawl_rejects_missing_url(server):
    """POST /api/crawl with no body returns 422 (validation error)."""
    r = httpx.post(f"{server}/api/crawl", json={})
    assert r.status_code == 422


def test_crawl_rejects_invalid_protocol(server):
    """ftp:// URLs are blocked at the route level."""
    r = httpx.post(f"{server}/api/crawl", json={"url": "ftp://example.com"})
    assert r.status_code == 400


def test_crawl_rejects_localhost(server):
    """localhost URLs are blocked (SSRF protection)."""
    r = httpx.post(f"{server}/api/crawl", json={"url": "http://localhost/secret"})
    assert r.status_code == 400


def test_crawl_rejects_private_ip(server):
    """Private IP ranges are blocked (SSRF protection)."""
    r = httpx.post(f"{server}/api/crawl", json={"url": "http://192.168.1.1/admin"})
    assert r.status_code == 400


def test_crawl_unknown_job_returns_404(server):
    """Polling a non-existent job_id returns 404."""
    r = httpx.get(f"{server}/api/crawl/does-not-exist-xyz")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Session — validation without real KB
# ---------------------------------------------------------------------------

def test_session_rejects_missing_kb_id(server):
    """POST /api/session with no body returns 422."""
    r = httpx.post(f"{server}/api/session", json={})
    assert r.status_code == 422


def test_session_rejects_unknown_kb(server):
    """Creating a session against a non-existent knowledge base returns 404."""
    r = httpx.post(f"{server}/api/session", json={"knowledge_base_id": "ghost-kb-id"})
    assert r.status_code == 404


def test_session_unknown_id_returns_404(server):
    """GET /api/session/:id for unknown session returns 404."""
    r = httpx.get(f"{server}/api/session/ghost-session-id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Chat — validation without real session
# ---------------------------------------------------------------------------

def test_chat_unknown_session_returns_404(server):
    """Sending a message to a non-existent session returns 404."""
    r = httpx.post(f"{server}/api/chat/ghost-session-id", json={"message": "hello"})
    assert r.status_code == 404


def test_chat_rejects_missing_message(server):
    """POST /api/chat/:id with no message field returns 422."""
    r = httpx.post(f"{server}/api/chat/any-session-id", json={})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Brief — validation without real session
# ---------------------------------------------------------------------------

def test_brief_unknown_session_returns_404(server):
    """Generating a brief for a non-existent session returns 404."""
    r = httpx.post(f"{server}/api/brief/ghost-session-id")
    assert r.status_code == 404
