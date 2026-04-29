"""
Integration tests for GET /api/portal/sites.
DB and auth mocked — no credentials required.
"""

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
    "DATABASE_URL": "postgresql://fake",
}

FAKE_USER_A = {
    "user_id": "usr_aaa",
    "email": "usera@test.com",
    "display_name": "User A",
    "google_sub": "sub-a",
    "created_at": 1000000,
    "last_login_at": 1000001,
}

FAKE_USER_B = {
    "user_id": "usr_bbb",
    "email": "userb@test.com",
    "display_name": "User B",
    "google_sub": "sub-b",
    "created_at": 1000000,
    "last_login_at": 1000001,
}

FAKE_SITE = {
    "kb_id": "finfloo",
    "url": "https://finfloo.com",
    "name": "Finfloo",
    "token": "finfloo",
    "created_at": 1000000,
    "last_crawled_at": 1000500,
    "pages_indexed": 12,
}


def _session_cookie(user_id: str) -> str:
    return URLSafeTimedSerializer(SECRET).dumps({"user_id": user_id})


@pytest.fixture()
def client():
    with patch.dict("os.environ", PORTAL_ENV):
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestListSites:

    def test_authenticated_user_with_one_site(self, client):
        with patch("app.routers.auth.db_get_user_by_id", new_callable=AsyncMock, return_value=FAKE_USER_A), \
             patch("app.routers.portal.db_get_user_sites", new_callable=AsyncMock, return_value=[FAKE_SITE]):
            resp = client.get(
                "/api/portal/sites",
                cookies={"contextus_portal_session": _session_cookie("usr_aaa")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sites"]) == 1
        assert data["sites"][0]["kb_id"] == "finfloo"
        assert data["sites"][0]["token"] == "finfloo"

    def test_authenticated_user_with_no_sites(self, client):
        with patch("app.routers.auth.db_get_user_by_id", new_callable=AsyncMock, return_value=FAKE_USER_A), \
             patch("app.routers.portal.db_get_user_sites", new_callable=AsyncMock, return_value=[]):
            resp = client.get(
                "/api/portal/sites",
                cookies={"contextus_portal_session": _session_cookie("usr_aaa")},
            )
        assert resp.status_code == 200
        assert resp.json() == {"sites": []}

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/portal/sites")
        assert resp.status_code == 401

    def test_tenant_isolation_user_a_sees_only_own_sites(self, client):
        site_a = {**FAKE_SITE, "kb_id": "finfloo", "name": "Finfloo"}
        site_b = {**FAKE_SITE, "kb_id": "other_kb", "name": "Other"}

        with patch("app.routers.auth.db_get_user_by_id", new_callable=AsyncMock, return_value=FAKE_USER_A), \
             patch("app.routers.portal.db_get_user_sites", new_callable=AsyncMock, return_value=[site_a]) as mock_sites:
            resp = client.get(
                "/api/portal/sites",
                cookies={"contextus_portal_session": _session_cookie("usr_aaa")},
            )
            mock_sites.assert_called_once_with("usr_aaa")

        assert resp.status_code == 200
        kb_ids = [s["kb_id"] for s in resp.json()["sites"]]
        assert "finfloo" in kb_ids
        assert "other_kb" not in kb_ids

    def test_site_name_present(self, client):
        with patch("app.routers.auth.db_get_user_by_id", new_callable=AsyncMock, return_value=FAKE_USER_A), \
             patch("app.routers.portal.db_get_user_sites", new_callable=AsyncMock, return_value=[FAKE_SITE]):
            resp = client.get(
                "/api/portal/sites",
                cookies={"contextus_portal_session": _session_cookie("usr_aaa")},
            )
        site = resp.json()["sites"][0]
        assert site["name"] == "Finfloo"
        assert site["url"] == "https://finfloo.com"

    def test_site_with_no_kb_row_returns_null_fields(self, client):
        site_no_kb = {
            "kb_id": "orphan_kb",
            "url": "https://orphan.com",
            "name": None,
            "token": "orphan_kb",
            "created_at": 1000000,
            "last_crawled_at": None,
            "pages_indexed": None,
        }
        with patch("app.routers.auth.db_get_user_by_id", new_callable=AsyncMock, return_value=FAKE_USER_A), \
             patch("app.routers.portal.db_get_user_sites", new_callable=AsyncMock, return_value=[site_no_kb]):
            resp = client.get(
                "/api/portal/sites",
                cookies={"contextus_portal_session": _session_cookie("usr_aaa")},
            )
        site = resp.json()["sites"][0]
        assert site["last_crawled_at"] is None
        assert site["pages_indexed"] is None
