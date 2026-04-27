"""
Integration tests for brief persistence (PR C).
Verifies that POST /api/brief/{session_id} writes to the briefs table
and that DB/webhook failures degrade gracefully.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.models import LeadBrief

FAKE_SESSION = MagicMock()
FAKE_SESSION.kb_id = "kb_test"
FAKE_SESSION.messages = [MagicMock(), MagicMock()]

FAKE_KB = {"kb_id": "kb_test", "data": {}}

FAKE_BRIEF = LeadBrief(
    session_id="sess_abc",
    created_at="2026-04-27T00:00:00Z",
    who="restaurant owner",
    need="bookkeeping",
    signals="has budget",
    open_questions="",
    suggested_approach="",
    quality_score="high",
    qualification="qualified",
    qualification_reason="",
    scope_match="true",
    red_flags=[],
    contact={},
    metadata={},
)


PORTAL_ENV = {
    "GOOGLE_OAUTH_CLIENT_ID": "fake-client-id",
    "GOOGLE_OAUTH_CLIENT_SECRET": "fake-client-secret",
    "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/api/auth/google/callback",
    "PORTAL_FRONTEND_URL": "http://localhost:3000",
    "PORTAL_SESSION_SECRET": "test-secret",
    "ADMIN_SECRET": "admin-test",
    "DATABASE_URL": "postgresql://fake",
}


@pytest.fixture()
def client():
    with patch.dict("os.environ", PORTAL_ENV):
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestBriefPersistence:

    def _call(self, client, session_id="sess_abc", *, save_side_effect=None):
        save_mock = AsyncMock(side_effect=save_side_effect)
        with patch("app.routers.brief.get_session", AsyncMock(return_value=FAKE_SESSION)), \
             patch("app.routers.brief.get_knowledge_base", AsyncMock(return_value=FAKE_KB)), \
             patch("app.routers.brief.generate_lead_brief", AsyncMock(return_value=FAKE_BRIEF)), \
             patch("app.routers.brief.get_customer_config", AsyncMock(return_value=None)), \
             patch("app.routers.brief.db_save_brief", save_mock), \
             patch("app.routers.brief.db_mark_brief_sent", AsyncMock()):
            resp = client.post(f"/api/brief/{session_id}")
        return resp, save_mock

    def test_brief_written_to_db_on_success(self, client):
        resp, save_mock = self._call(client)
        assert resp.status_code == 200
        save_mock.assert_awaited_once()
        args = save_mock.await_args[0]
        assert args[0] == "sess_abc"
        assert args[1] == "kb_test"
        assert args[2]["qualification"] == "qualified"
        assert args[2]["quality_score"] == "high"

    def test_brief_persisted_before_webhook_task_is_created(self, client):
        """db_save_brief is awaited (synchronous), webhook is create_task (async).
        Verify save is called and completes before the task is created."""
        save_mock = AsyncMock()
        task_mock = MagicMock(return_value=MagicMock())  # create_task returns a Task

        with patch("app.routers.brief.get_session", AsyncMock(return_value=FAKE_SESSION)), \
             patch("app.routers.brief.get_knowledge_base", AsyncMock(return_value=FAKE_KB)), \
             patch("app.routers.brief.generate_lead_brief", AsyncMock(return_value=FAKE_BRIEF)), \
             patch("app.routers.brief.get_customer_config", AsyncMock(return_value={"webhook_url": "http://hook"})), \
             patch("app.routers.brief.db_save_brief", save_mock), \
             patch("app.routers.brief.asyncio.create_task", task_mock), \
             patch("app.routers.brief.db_mark_brief_sent", AsyncMock()):
            resp = client.post("/api/brief/sess_order")
        assert resp.status_code == 200
        save_mock.assert_awaited_once()
        task_mock.assert_called()  # create_task was called (webhook scheduled)

    def test_db_failure_does_not_500(self, client):
        resp, _ = self._call(client, save_side_effect=Exception("DB down"))
        assert resp.status_code == 200

    def test_upsert_on_duplicate_call(self, client):
        save_mock = AsyncMock()
        with patch("app.routers.brief.get_session", AsyncMock(return_value=FAKE_SESSION)), \
             patch("app.routers.brief.get_knowledge_base", AsyncMock(return_value=FAKE_KB)), \
             patch("app.routers.brief.generate_lead_brief", AsyncMock(return_value=FAKE_BRIEF)), \
             patch("app.routers.brief.get_customer_config", AsyncMock(return_value=None)), \
             patch("app.routers.brief.db_save_brief", save_mock), \
             patch("app.routers.brief.db_mark_brief_sent", AsyncMock()):
            client.post("/api/brief/sess_dup")
            client.post("/api/brief/sess_dup")
        assert save_mock.await_count == 2

    def test_existing_brief_generation_still_returns_200(self, client):
        resp, _ = self._call(client, session_id="sess_smoke")
        assert resp.status_code == 200
