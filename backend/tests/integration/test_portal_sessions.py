"""
Integration tests for inbox endpoints (PR D).
GET /api/portal/sessions and GET /api/portal/sessions/{session_id}
"""

import base64
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

SECRET = "test-portal-secret"
PORTAL_ENV = {
    "GOOGLE_OAUTH_CLIENT_ID": "fake-client-id",
    "GOOGLE_OAUTH_CLIENT_SECRET": "fake-client-secret",
    "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/api/auth/google/callback",
    "PORTAL_FRONTEND_URL": "http://localhost:3000",
    "PORTAL_SESSION_SECRET": SECRET,
    "ADMIN_SECRET": "admin-secret-test",
    "DATABASE_URL": "postgresql://fake",
}

FAKE_USER_A = {
    "user_id": "usr_aaa",
    "email": "usera@test.com",
    "display_name": "User A",
    "google_sub": "sub-aaa",
    "created_at": 1000000,
    "last_login_at": 1000001,
}

FAKE_USER_B = {
    "user_id": "usr_bbb",
    "email": "userb@test.com",
    "display_name": "User B",
    "google_sub": "sub-bbb",
    "created_at": 1000000,
    "last_login_at": 1000001,
}

MESSAGES = [
    {"role": "bot", "text": "halo, ada yang bisa kami bantu?"},
    {"role": "user", "text": "do you handle restaurants?"},
]

FAKE_SESSION_ROW = {
    "session_id": "sess_001",
    "kb_id": "kb_finfloo",
    "created_at": 1000000,
    "updated_at": 1000100,
    "message_count": 2,
    "contact_captured": True,
    "contact_value": "budi@example.com",
    "messages": MESSAGES,
    "brief_sent": True,
    "qualification": "qualified",
    "quality_score": "high",
}

FAKE_BRIEF = {
    "who": "restaurant owner",
    "need": "bookkeeping",
    "signals": "has budget",
    "open_questions": "",
    "suggested_approach": "",
    "quality_score": "high",
    "qualification": "qualified",
    "qualification_reason": "",
    "scope_match": "true",
    "red_flags": [],
    "contact": {"email": "budi@example.com"},
}


@pytest.fixture()
def client():
    with patch.dict("os.environ", PORTAL_ENV):
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def _session_cookie(user_id: str) -> str:
    return URLSafeTimedSerializer(SECRET).dumps({"user_id": user_id})


def _decode_cursor(cursor: str) -> int:
    return int(base64.b64decode(cursor).decode())


class TestListSessions:

    def test_authenticated_user_with_sessions(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_list_sessions", AsyncMock(return_value=[FAKE_SESSION_ROW])):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 1
        s = data["sessions"][0]
        assert s["session_id"] == "sess_001"
        assert s["qualification"] == "qualified"
        assert s["quality_score"] == "high"
        assert s["contact_value"] == "budi@example.com"

    def test_authenticated_user_with_no_sessions(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_list_sessions", AsyncMock(return_value=[])):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions"] == []
        assert data["next_cursor"] is None

    def test_sessions_without_briefs_have_null_qualification(self, client):
        row = {**FAKE_SESSION_ROW, "qualification": None, "quality_score": None, "brief_sent": False}
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_list_sessions", AsyncMock(return_value=[row])):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        s = resp.json()["sessions"][0]
        assert s["qualification"] is None
        assert s["quality_score"] is None

    def test_preview_is_first_user_message_truncated(self, client):
        long_msg = "a" * 100
        row = {**FAKE_SESSION_ROW, "messages": [
            {"role": "bot", "text": "hello"},
            {"role": "user", "text": long_msg},
        ]}
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_list_sessions", AsyncMock(return_value=[row])):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["sessions"][0]["preview"] == "a" * 80

    def test_preview_falls_back_to_first_message_when_no_user_role(self, client):
        row = {**FAKE_SESSION_ROW, "messages": [{"role": "bot", "text": "hello from bot"}]}
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_list_sessions", AsyncMock(return_value=[row])):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["sessions"][0]["preview"] == "hello from bot"

    def test_pagination_returns_cursor_when_full_page(self, client):
        rows = [
            {**FAKE_SESSION_ROW, "session_id": f"sess_{i}", "updated_at": 1000100 - i}
            for i in range(2)
        ]
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_list_sessions", AsyncMock(return_value=rows)):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo&limit=2",
                cookies={"contextus_portal_session": cookie},
            )
        data = resp.json()
        assert len(data["sessions"]) == 2
        assert data["next_cursor"] is not None
        assert _decode_cursor(data["next_cursor"]) == rows[-1]["updated_at"]

    def test_pagination_last_page_has_no_cursor(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_list_sessions", AsyncMock(return_value=[FAKE_SESSION_ROW])):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo&limit=50",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["next_cursor"] is None

    def test_messages_as_json_string_is_parsed(self, client):
        import json
        row = {**FAKE_SESSION_ROW, "messages": json.dumps(MESSAGES)}
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_list_sessions", AsyncMock(return_value=[row])):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert resp.json()["sessions"][0]["preview"] == "do you handle restaurants?"

    def test_missing_kb_id_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)):
            resp = client.get(
                "/api/portal/sessions",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/portal/sessions?kb_id=kb_finfloo")
        assert resp.status_code == 401

    def test_tenant_isolation_wrong_kb_id_returns_403(self, client):
        cookie = _session_cookie("usr_bbb")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_B)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=False)):
            resp = client.get(
                "/api/portal/sessions?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 403


class TestGetSessionDetail:

    def _detail_row(self, brief_data=None):
        return {**FAKE_SESSION_ROW, "brief_data": brief_data}

    def test_valid_session_returns_200(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.portal.db_get_session", AsyncMock(return_value=self._detail_row(FAKE_BRIEF))), \
             patch("app.routers.portal.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.get(
                "/api/portal/sessions/sess_001",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["session_id"] == "sess_001"
        assert data["brief"]["qualification"] == "qualified"

    def test_brief_is_null_when_no_brief_row(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.portal.db_get_session", AsyncMock(return_value=self._detail_row(None))), \
             patch("app.routers.portal.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.get(
                "/api/portal/sessions/sess_001",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert resp.json()["brief"] is None

    def test_messages_returned_as_is(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.portal.db_get_session", AsyncMock(return_value=self._detail_row())), \
             patch("app.routers.portal.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.get(
                "/api/portal/sessions/sess_001",
                cookies={"contextus_portal_session": cookie},
            )
        msgs = resp.json()["session"]["messages"]
        assert msgs[0]["role"] == "bot"
        assert msgs[1]["role"] == "user"

    def test_brief_data_as_json_string_is_parsed(self, client):
        import json
        row = {**FAKE_SESSION_ROW, "brief_data": json.dumps(FAKE_BRIEF)}
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.portal.db_get_session", AsyncMock(return_value=row)), \
             patch("app.routers.portal.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.get(
                "/api/portal/sessions/sess_001",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert resp.json()["brief"]["qualification"] == "qualified"

    def test_session_not_found_returns_404(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.portal.db_get_session", AsyncMock(return_value=None)):
            resp = client.get(
                "/api/portal/sessions/sess_missing",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/portal/sessions/sess_001")
        assert resp.status_code == 401

    def test_tenant_isolation_other_users_session_returns_403(self, client):
        cookie = _session_cookie("usr_bbb")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_B)), \
             patch("app.routers.portal.db_get_session", AsyncMock(return_value=self._detail_row())), \
             patch("app.routers.portal.db_user_has_kb_access", AsyncMock(return_value=False)):
            resp = client.get(
                "/api/portal/sessions/sess_001",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 403
