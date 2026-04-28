"""
Integration tests for KB endpoints (PR E + PR F).
GET /api/portal/kb
POST /api/portal/kb/enrich
PATCH /api/portal/kb/pills
PATCH /api/portal/kb/greeting
PATCH /api/portal/kb/custom-instructions
GET /api/session (greeting field)
"""

import json
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

_KB_DATA_DICT = {
    "job_id": "kb_finfloo",
    "status": "complete",
    "progress": "",
    "pages_found": 12,
    "quality_tier": "rich",
    "company_profile": {
        "name": "Finfloo",
        "industry": "Accounting & bookkeeping",
        "services": ["Monthly bookkeeping", "Tax filing", "Payroll"],
        "out_of_scope": ["Investment advice"],
        "location": None,
        "contact": None,
        "summary": "Finfloo is a Jakarta-based bookkeeping firm.",
        "gaps": [],
        "pill_suggestions": None,
        "language": "en",
        "custom_instructions": "Always greet in Indonesian.",
    },
    "chunks": [
        {"id": "chunk_crawled", "source": "https://finfloo.com/page", "text": "Crawled content", "word_count": 2},
        {"id": "chunk_qa1", "source": "interview:What are your prices?", "text": "Starts at IDR 2.5M/month.", "word_count": 5},
        {"id": "chunk_qa2", "source": "interview:Do you handle payroll?", "text": "Yes we do.", "word_count": 3},
    ],
    "suggested_pills": ["Daftar sekarang", "Lihat harga", "Hubungi kami"],
    "language": "en",
    "created_at": 1000000,
}

FAKE_KB_DATA = json.dumps(_KB_DATA_DICT)

FAKE_KB_ROW = {
    "kb_data": FAKE_KB_DATA,
    "updated_at": 1700000000,
    "greeting": "Halo, ada yang bisa kami bantu?",
}


@pytest.fixture()
def client():
    with patch.dict("os.environ", PORTAL_ENV):
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def _session_cookie(user_id: str) -> str:
    return URLSafeTimedSerializer(SECRET).dumps({"user_id": user_id})


class TestGetKB:

    def test_authenticated_valid_kb_returns_200(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=FAKE_KB_ROW)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["kb_id"] == "kb_finfloo"

    def test_enriched_chunks_contains_only_interview_chunks(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=FAKE_KB_ROW)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        chunks = resp.json()["enriched_chunks"]
        assert len(chunks) == 2
        questions = [c["question"] for c in chunks]
        assert "What are your prices?" in questions
        assert "Do you handle payroll?" in questions

    def test_enriched_chunks_strips_interview_prefix(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=FAKE_KB_ROW)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        chunk = next(c for c in resp.json()["enriched_chunks"] if "prices" in c["question"])
        assert chunk["question"] == "What are your prices?"
        assert chunk["answer"] == "Starts at IDR 2.5M/month."
        assert chunk["word_count"] == 5
        assert chunk["id"] == "chunk_qa1"

    def test_enriched_chunks_empty_when_no_interview_chunks(self, client):
        row = {
            **FAKE_KB_ROW,
            "kb_data": json.dumps({
                **_KB_DATA_DICT,
                "chunks": [
                    {"id": "c1", "source": "https://finfloo.com", "text": "Crawled", "word_count": 1}
                ],
            }),
        }
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=row)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["enriched_chunks"] == []

    def test_company_profile_fields_match_kb(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=FAKE_KB_ROW)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        cp = resp.json()["company_profile"]
        assert cp["name"] == "Finfloo"
        assert cp["industry"] == "Accounting & bookkeeping"
        assert cp["services"] == "Monthly bookkeeping, Tax filing, Payroll"
        assert cp["out_of_scope"] == "Investment advice"
        assert cp["summary"] == "Finfloo is a Jakarta-based bookkeeping firm."
        assert cp["last_crawled_at"] == 1700000000
        assert cp["pages_indexed"] == 12

    def test_pills_returned_from_kb(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=FAKE_KB_ROW)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["pills"] == ["Daftar sekarang", "Lihat harga", "Hubungi kami"]

    def test_pills_empty_list_when_none(self, client):
        row = {**FAKE_KB_ROW, "kb_data": json.dumps({**_KB_DATA_DICT, "suggested_pills": []})}
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=row)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["pills"] == []

    def test_greeting_null_when_not_set(self, client):
        row = {**FAKE_KB_ROW, "greeting": None}
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=row)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["greeting"] is None

    def test_greeting_returned_when_set(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=FAKE_KB_ROW)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["greeting"] == "Halo, ada yang bisa kami bantu?"

    def test_custom_instructions_null_when_not_set(self, client):
        cp = {**_KB_DATA_DICT["company_profile"], "custom_instructions": None}
        row = {**FAKE_KB_ROW, "kb_data": json.dumps({**_KB_DATA_DICT, "company_profile": cp})}
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=row)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["custom_instructions"] is None

    def test_custom_instructions_returned_when_set(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=FAKE_KB_ROW)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.json()["custom_instructions"] == "Always greet in Indonesian."

    def test_kb_not_found_returns_404(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_get_kb", AsyncMock(return_value=None)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_unknown",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 404

    def test_kb_id_not_accessible_returns_403(self, client):
        cookie = _session_cookie("usr_bbb")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_B)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=False)):
            resp = client.get(
                "/api/portal/kb?kb_id=kb_finfloo",
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/portal/kb?kb_id=kb_finfloo")
        assert resp.status_code == 401


# ── Shared fake KB object for write endpoint tests ────────────────────────────

_FAKE_KB_COMPLETE = {
    "job_id": "kb_finfloo",
    "status": "complete",
    "progress": "",
    "pages_found": 12,
    "quality_tier": "rich",
    "company_profile": {
        "name": "Finfloo",
        "industry": "Accounting & bookkeeping",
        "services": ["Monthly bookkeeping"],
        "out_of_scope": [],
        "location": None,
        "contact": None,
        "summary": "Finfloo bookkeeping",
        "gaps": [],
        "pill_suggestions": None,
        "language": "en",
        "custom_instructions": None,
    },
    "chunks": [],
    "suggested_pills": ["A", "B", "C"],
    "language": "en",
    "created_at": 1000000,
}

_FAKE_KB_NO_PROFILE = {**_FAKE_KB_COMPLETE, "company_profile": None}
_FAKE_KB_NOT_READY = {**_FAKE_KB_COMPLETE, "status": "analyzing"}


def _make_kb(data: dict):
    """Return a KnowledgeBase instance from a dict (for use as mock return value)."""
    from app.models import KnowledgeBase
    return KnowledgeBase.model_validate(data)


_FAKE_CP = {
    "name": "Finfloo",
    "industry": "Accounting",
    "services": ["Bookkeeping"],
    "out_of_scope": [],
    "location": None,
    "contact": None,
    "summary": "Finfloo",
    "gaps": [],
    "language": "en",
    "custom_instructions": None,
}


class TestPortalEnrich:

    def test_valid_request_returns_200(self, client):
        cookie = _session_cookie("usr_aaa")
        from app.models import CompanyProfile
        fake_cp = CompanyProfile.model_validate(_FAKE_CP)
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.get_knowledge_base", AsyncMock(return_value=_make_kb(_FAKE_KB_COMPLETE))), \
             patch("app.routers.portal.check_rate_limit", AsyncMock(return_value=True)), \
             patch("app.routers.portal.enrich_kb", AsyncMock(return_value=fake_cp)):
            resp = client.post(
                "/api/portal/kb/enrich",
                json={"kb_id": "kb_finfloo", "question": "What is your price?", "answer": "IDR 2.5M/month"},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200

    def test_empty_question_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)):
            resp = client.post(
                "/api/portal/kb/enrich",
                json={"kb_id": "kb_finfloo", "question": "", "answer": "Some answer"},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_question_too_long_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)):
            resp = client.post(
                "/api/portal/kb/enrich",
                json={"kb_id": "kb_finfloo", "question": "q" * 201, "answer": "Some answer"},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_empty_answer_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)):
            resp = client.post(
                "/api/portal/kb/enrich",
                json={"kb_id": "kb_finfloo", "question": "What is your price?", "answer": ""},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_answer_too_long_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)):
            resp = client.post(
                "/api/portal/kb/enrich",
                json={"kb_id": "kb_finfloo", "question": "Q?", "answer": "a" * 2001},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_kb_not_ready_returns_400(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.get_knowledge_base", AsyncMock(return_value=_make_kb(_FAKE_KB_NOT_READY))):
            resp = client.post(
                "/api/portal/kb/enrich",
                json={"kb_id": "kb_finfloo", "question": "Q?", "answer": "A"},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "kb_not_ready"

    def test_rate_limit_exceeded_returns_429(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.get_knowledge_base", AsyncMock(return_value=_make_kb(_FAKE_KB_COMPLETE))), \
             patch("app.routers.portal.check_rate_limit", AsyncMock(return_value=False)):
            resp = client.post(
                "/api/portal/kb/enrich",
                json={"kb_id": "kb_finfloo", "question": "Q?", "answer": "A"},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 429
        assert resp.json()["detail"]["error"] == "rate_limit_exceeded"
        assert "retry_after" in resp.json()["detail"]

    def test_tenant_isolation_returns_403(self, client):
        cookie = _session_cookie("usr_bbb")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_B)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=False)):
            resp = client.post(
                "/api/portal/kb/enrich",
                json={"kb_id": "kb_finfloo", "question": "Q?", "answer": "A"},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/portal/kb/enrich",
            json={"kb_id": "kb_finfloo", "question": "Q?", "answer": "A"},
        )
        assert resp.status_code == 401


class TestPortalPills:

    def test_valid_3_pills_returns_200(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.get_knowledge_base", AsyncMock(return_value=_make_kb(_FAKE_KB_COMPLETE))), \
             patch("app.routers.portal.update_pills_kb", AsyncMock(return_value=None)):
            resp = client.patch(
                "/api/portal/kb/pills",
                json={"kb_id": "kb_finfloo", "pills": ["A", "B", "C"]},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_2_pills_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.patch(
                "/api/portal/kb/pills",
                json={"kb_id": "kb_finfloo", "pills": ["A", "B"]},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_4_pills_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.patch(
                "/api/portal/kb/pills",
                json={"kb_id": "kb_finfloo", "pills": ["A", "B", "C", "D"]},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_empty_string_pill_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.patch(
                "/api/portal/kb/pills",
                json={"kb_id": "kb_finfloo", "pills": ["A", "", "C"]},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_tenant_isolation_returns_403(self, client):
        cookie = _session_cookie("usr_bbb")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_B)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=False)):
            resp = client.patch(
                "/api/portal/kb/pills",
                json={"kb_id": "kb_finfloo", "pills": ["A", "B", "C"]},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.patch(
            "/api/portal/kb/pills",
            json={"kb_id": "kb_finfloo", "pills": ["A", "B", "C"]},
        )
        assert resp.status_code == 401


class TestPortalGreeting:

    def test_valid_greeting_returns_200(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_update_greeting", AsyncMock(return_value=None)):
            resp = client.patch(
                "/api/portal/kb/greeting",
                json={"kb_id": "kb_finfloo", "greeting": "Hello!"},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_null_greeting_clears_to_null(self, client):
        cookie = _session_cookie("usr_aaa")
        captured = {}
        async def mock_update(kb_id, greeting):
            captured["greeting"] = greeting
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_update_greeting", mock_update):
            resp = client.patch(
                "/api/portal/kb/greeting",
                json={"kb_id": "kb_finfloo", "greeting": None},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert captured["greeting"] is None

    def test_empty_string_clears_to_null(self, client):
        cookie = _session_cookie("usr_aaa")
        captured = {}
        async def mock_update(kb_id, greeting):
            captured["greeting"] = greeting
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_update_greeting", mock_update):
            resp = client.patch(
                "/api/portal/kb/greeting",
                json={"kb_id": "kb_finfloo", "greeting": ""},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert captured["greeting"] is None

    def test_greeting_too_long_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.patch(
                "/api/portal/kb/greeting",
                json={"kb_id": "kb_finfloo", "greeting": "g" * 201},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_greeting_trimmed(self, client):
        cookie = _session_cookie("usr_aaa")
        captured = {}
        async def mock_update(kb_id, greeting):
            captured["greeting"] = greeting
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.db_update_greeting", mock_update):
            resp = client.patch(
                "/api/portal/kb/greeting",
                json={"kb_id": "kb_finfloo", "greeting": "  Hello!  "},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert captured["greeting"] == "Hello!"

    def test_tenant_isolation_returns_403(self, client):
        cookie = _session_cookie("usr_bbb")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_B)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=False)):
            resp = client.patch(
                "/api/portal/kb/greeting",
                json={"kb_id": "kb_finfloo", "greeting": "Hello"},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.patch(
            "/api/portal/kb/greeting",
            json={"kb_id": "kb_finfloo", "greeting": "Hello"},
        )
        assert resp.status_code == 401


class TestPortalCustomInstructions:

    def test_valid_string_returns_200(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.get_knowledge_base", AsyncMock(return_value=_make_kb(_FAKE_KB_COMPLETE))), \
             patch("app.routers.portal.update_custom_instructions_kb", AsyncMock(return_value=None)):
            resp = client.patch(
                "/api/portal/kb/custom-instructions",
                json={"kb_id": "kb_finfloo", "custom_instructions": "Be formal."},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_null_clears_field(self, client):
        cookie = _session_cookie("usr_aaa")
        captured = {}
        async def mock_update(kb, kb_id, value, permanent):
            captured["value"] = value
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.get_knowledge_base", AsyncMock(return_value=_make_kb(_FAKE_KB_COMPLETE))), \
             patch("app.routers.portal.update_custom_instructions_kb", mock_update):
            resp = client.patch(
                "/api/portal/kb/custom-instructions",
                json={"kb_id": "kb_finfloo", "custom_instructions": None},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 200
        assert captured["value"] is None

    def test_too_long_returns_422(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)):
            resp = client.patch(
                "/api/portal/kb/custom-instructions",
                json={"kb_id": "kb_finfloo", "custom_instructions": "x" * 2001},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 422

    def test_no_company_profile_returns_400(self, client):
        cookie = _session_cookie("usr_aaa")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_A)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=True)), \
             patch("app.routers.portal.get_knowledge_base", AsyncMock(return_value=_make_kb(_FAKE_KB_NO_PROFILE))):
            resp = client.patch(
                "/api/portal/kb/custom-instructions",
                json={"kb_id": "kb_finfloo", "custom_instructions": "Be formal."},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "kb_not_ready"

    def test_tenant_isolation_returns_403(self, client):
        cookie = _session_cookie("usr_bbb")
        with patch("app.routers.auth.db_get_user_by_id", AsyncMock(return_value=FAKE_USER_B)), \
             patch("app.routers.auth.db_user_has_kb_access", AsyncMock(return_value=False)):
            resp = client.patch(
                "/api/portal/kb/custom-instructions",
                json={"kb_id": "kb_finfloo", "custom_instructions": "Be formal."},
                cookies={"contextus_portal_session": cookie},
            )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.patch(
            "/api/portal/kb/custom-instructions",
            json={"kb_id": "kb_finfloo", "custom_instructions": "Be formal."},
        )
        assert resp.status_code == 401


class TestSessionGreeting:

    def _fake_kb(self):
        from app.models import KnowledgeBase
        return KnowledgeBase.model_validate({
            "job_id": "kb_finfloo",
            "status": "complete",
            "progress": "",
            "pages_found": 0,
            "company_profile": {
                "name": "Finfloo",
                "industry": "Accounting",
                "services": [],
                "out_of_scope": [],
                "summary": "",
                "gaps": [],
                "language": "en",
            },
            "chunks": [],
            "suggested_pills": ["A", "B"],
            "language": "en",
            "created_at": 1000000,
        })

    def test_session_response_includes_greeting_when_set(self, client):
        config = {"greeting": "Halo!"}
        with patch("app.routers.session.get_knowledge_base", AsyncMock(return_value=self._fake_kb())), \
             patch("app.routers.session.save_session", AsyncMock(return_value=None)), \
             patch("app.services.analytics.track"), \
             patch("app.routers.session.get_customer_config", AsyncMock(return_value=config)):
            resp = client.post("/api/session", json={"knowledge_base_id": "kb_finfloo"})
        assert resp.status_code == 200
        assert resp.json()["greeting"] == "Halo!"

    def test_session_response_greeting_null_when_not_set(self, client):
        config = {"greeting": None}
        with patch("app.routers.session.get_knowledge_base", AsyncMock(return_value=self._fake_kb())), \
             patch("app.routers.session.save_session", AsyncMock(return_value=None)), \
             patch("app.services.analytics.track"), \
             patch("app.routers.session.get_customer_config", AsyncMock(return_value=config)):
            resp = client.post("/api/session", json={"knowledge_base_id": "kb_finfloo"})
        assert resp.status_code == 200
        assert resp.json()["greeting"] is None

    def test_session_response_existing_fields_unchanged(self, client):
        config = {"greeting": "Hi!"}
        with patch("app.routers.session.get_knowledge_base", AsyncMock(return_value=self._fake_kb())), \
             patch("app.routers.session.save_session", AsyncMock(return_value=None)), \
             patch("app.services.analytics.track"), \
             patch("app.routers.session.get_customer_config", AsyncMock(return_value=config)):
            resp = client.post("/api/session", json={"knowledge_base_id": "kb_finfloo"})
        data = resp.json()
        assert "session_id" in data
        assert data["pills"] == ["A", "B"]
        assert data["language"] == "en"
        assert data["name"] == "Finfloo"
