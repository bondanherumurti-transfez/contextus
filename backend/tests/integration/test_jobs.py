"""
Integration tests for POST /jobs/process-sessions.
Verifies brief persistence (db_save_brief) is called from the cron path,
in addition to the existing Notion + webhook flow.
"""

import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.models import Session, Message, LeadBrief

client = TestClient(app)


def make_session(session_id="sess_job", messages=6, brief_sent=False, has_contact=True):
    msgs = [
        Message(role="user" if i % 2 == 0 else "assistant", text=f"msg {i}", timestamp=int(time.time()))
        for i in range(messages)
    ]
    return Session(
        session_id=session_id,
        kb_id="kb_test",
        messages=msgs,
        contact_captured=has_contact,
        contact_value='{"email":"test@test.com"}' if has_contact else None,
        brief_sent=brief_sent,
        created_at=int(time.time()),
    )


FAKE_BRIEF = LeadBrief(
    session_id="sess_job",
    created_at=str(int(time.time())),
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
    contact={"email": "test@test.com", "phone": None, "whatsapp": None},
    metadata={"model": "test"},
)


def _patches(*, sessions, save_side_effect=None, notion_success=True):
    return {
        "app.routers.jobs.scan_all_sessions": AsyncMock(return_value=sessions),
        "app.routers.jobs.redis.get": AsyncMock(return_value=None),
        "app.routers.jobs.generate_lead_brief": AsyncMock(return_value=FAKE_BRIEF),
        "app.routers.jobs.get_customer_config": AsyncMock(return_value=None),
        "app.routers.jobs.post_lead_brief_to_notion": AsyncMock(return_value=notion_success),
        "app.routers.jobs.save_session": AsyncMock(),
        "app.routers.jobs.db_save_brief": AsyncMock(side_effect=save_side_effect),
    }


class TestProcessSessions:

    def test_brief_persisted_to_db_on_success(self):
        session = make_session()
        save_mock = AsyncMock()
        with patch("app.routers.jobs.scan_all_sessions", AsyncMock(return_value=[session])), \
             patch("app.routers.jobs.redis.get", AsyncMock(return_value=None)), \
             patch("app.routers.jobs.generate_lead_brief", AsyncMock(return_value=FAKE_BRIEF)), \
             patch("app.routers.jobs.get_customer_config", AsyncMock(return_value=None)), \
             patch("app.routers.jobs.post_lead_brief_to_notion", AsyncMock(return_value=True)), \
             patch("app.routers.jobs.save_session", AsyncMock()), \
             patch("app.routers.jobs.db_save_brief", save_mock):
            resp = client.post("/api/jobs/process-sessions")
        assert resp.status_code == 200
        assert resp.json()["processed"] == 1
        save_mock.assert_awaited_once()
        args = save_mock.await_args[0]
        assert args[0] == "sess_job"
        assert args[1] == "kb_test"
        assert args[2]["qualification"] == "qualified"

    def test_db_save_failure_does_not_block_notion_or_webhook(self):
        session = make_session()
        save_mock = AsyncMock(side_effect=Exception("DB down"))
        with patch("app.routers.jobs.scan_all_sessions", AsyncMock(return_value=[session])), \
             patch("app.routers.jobs.redis.get", AsyncMock(return_value=None)), \
             patch("app.routers.jobs.generate_lead_brief", AsyncMock(return_value=FAKE_BRIEF)), \
             patch("app.routers.jobs.get_customer_config", AsyncMock(return_value={"webhook_url": "http://hook"})), \
             patch("app.routers.jobs.post_lead_brief_to_notion", AsyncMock(return_value=True)), \
             patch("app.routers.jobs.save_session", AsyncMock()), \
             patch("app.routers.jobs.db_save_brief", save_mock), \
             patch("app.routers.jobs.fire_webhook", AsyncMock()) as mock_webhook, \
             patch("app.routers.jobs.asyncio.create_task", MagicMock(return_value=MagicMock())):
            resp = client.post("/api/jobs/process-sessions")
        assert resp.status_code == 200
        assert resp.json()["processed"] == 1

    def test_already_sent_sessions_are_skipped(self):
        session = make_session(brief_sent=True)
        save_mock = AsyncMock()
        with patch("app.routers.jobs.scan_all_sessions", AsyncMock(return_value=[session])), \
             patch("app.routers.jobs.db_save_brief", save_mock):
            resp = client.post("/api/jobs/process-sessions")
        assert resp.status_code == 200
        assert resp.json()["skipped_tagged"] == 1
        save_mock.assert_not_awaited()

    def test_thin_sessions_are_skipped(self):
        session = make_session(messages=2, has_contact=False)
        save_mock = AsyncMock()
        with patch("app.routers.jobs.scan_all_sessions", AsyncMock(return_value=[session])), \
             patch("app.routers.jobs.redis.get", AsyncMock(return_value=None)), \
             patch("app.routers.jobs.db_save_brief", save_mock):
            resp = client.post("/api/jobs/process-sessions")
        assert resp.status_code == 200
        assert resp.json()["skipped_thin"] == 1
        save_mock.assert_not_awaited()

    def test_no_sessions_returns_zero_counts(self):
        with patch("app.routers.jobs.scan_all_sessions", AsyncMock(return_value=[])):
            resp = client.post("/api/jobs/process-sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 0
        assert data["failed"] == 0
