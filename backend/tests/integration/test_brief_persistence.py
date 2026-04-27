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


@pytest.fixture()
def client():
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

    def test_brief_persisted_before_webhook(self, client):
        call_order = []

        async def track_save(*a, **kw):
            call_order.append("save")

        async def track_webhook(*a, **kw):
            call_order.append("webhook")

        with patch("app.routers.brief.get_session", AsyncMock(return_value=FAKE_SESSION)), \
             patch("app.routers.brief.get_knowledge_base", AsyncMock(return_value=FAKE_KB)), \
             patch("app.routers.brief.generate_lead_brief", AsyncMock(return_value=FAKE_BRIEF)), \
             patch("app.routers.brief.get_customer_config", AsyncMock(return_value={"webhook_url": "http://hook"})), \
             patch("app.routers.brief.db_save_brief", AsyncMock(side_effect=track_save)), \
             patch("app.routers.brief.fire_webhook", AsyncMock(side_effect=track_webhook)), \
             patch("app.routers.brief.db_mark_brief_sent", AsyncMock()):
            client.post("/api/brief/sess_order")
        assert "save" in call_order
        assert call_order.index("save") == 0

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
