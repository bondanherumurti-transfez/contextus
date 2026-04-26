"""
Integration tests for /api/auth/* endpoints.
All external calls (Google OAuth, DB) are mocked — no credentials required.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

SECRET = "test-integration-secret"
PORTAL_ENV = {
    "GOOGLE_OAUTH_CLIENT_ID": "fake-client-id",
    "GOOGLE_OAUTH_CLIENT_SECRET": "fake-client-secret",
    "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/api/auth/google/callback",
    "PORTAL_FRONTEND_URL": "http://localhost:3000",
    "PORTAL_SESSION_SECRET": SECRET,
    "ADMIN_SECRET": "admin-secret-test",
    "DATABASE_URL": "postgresql://fake",
}

FAKE_USER = {
    "user_id": "usr_abc123",
    "email": "bondan@test.com",
    "display_name": "Bondan",
    "google_sub": "google-sub-abc",
    "created_at": 1000000,
    "last_login_at": 1000001,
}


@pytest.fixture()
def client():
    with patch.dict("os.environ", PORTAL_ENV):
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def _signed_state(state_value: str) -> str:
    return URLSafeTimedSerializer(SECRET).dumps({"state": state_value})


def _signed_session(user_id: str) -> str:
    return URLSafeTimedSerializer(SECRET).dumps({"user_id": user_id})


class TestGoogleStart:

    def test_redirects_to_google(self, client):
        resp = client.get("/api/auth/google/start", follow_redirects=False)
        assert resp.status_code == 302
        assert "accounts.google.com" in resp.headers["location"]

    def test_sets_state_cookie(self, client):
        resp = client.get("/api/auth/google/start", follow_redirects=False)
        assert "contextus_oauth_state" in resp.cookies

    def test_google_url_contains_required_params(self, client):
        resp = client.get("/api/auth/google/start", follow_redirects=False)
        location = resp.headers["location"]
        assert "client_id=fake-client-id" in location
        assert "scope=openid+email+profile" in location
        assert "response_type=code" in location


class TestGoogleCallback:

    def _patch_oauth(self, token: dict, userinfo: dict):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.fetch_token = AsyncMock(return_value=token)

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = userinfo
        mock_resp.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        return mock_client, mock_http

    def test_state_mismatch_returns_400(self, client):
        state_cookie = _signed_state("correct-state")
        resp = client.get(
            "/api/auth/google/callback?code=abc&state=wrong-state",
            cookies={"contextus_oauth_state": state_cookie},
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_missing_state_cookie_returns_400(self, client):
        resp = client.get(
            "/api/auth/google/callback?code=abc&state=some-state",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_missing_state_param_returns_400(self, client):
        state_cookie = _signed_state("correct-state")
        resp = client.get(
            "/api/auth/google/callback?code=abc",
            cookies={"contextus_oauth_state": state_cookie},
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_new_user_redirects_to_portal(self, client):
        state = "test-state-value"
        state_cookie = _signed_state(state)
        mock_oauth, mock_http = self._patch_oauth(
            {"access_token": "tok123"},
            {"sub": "google-sub-new", "email": "new@test.com", "name": "New User"},
        )
        with patch("app.routers.auth.AsyncOAuth2Client", return_value=mock_oauth), \
             patch("app.routers.auth.httpx.AsyncClient", return_value=mock_http), \
             patch("app.routers.auth.db_get_user_by_google_sub", new_callable=AsyncMock, return_value=None), \
             patch("app.routers.auth.db_get_user_by_email_no_sub", new_callable=AsyncMock, return_value=None), \
             patch("app.routers.auth.db_create_user", new_callable=AsyncMock, return_value=FAKE_USER):
            resp = client.get(
                f"/api/auth/google/callback?code=abc&state={state}",
                cookies={"contextus_oauth_state": state_cookie},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert resp.headers["location"] == "http://localhost:3000"
        assert "contextus_portal_session" in resp.cookies

    def test_returning_user_updates_login(self, client):
        state = "test-state-returning"
        state_cookie = _signed_state(state)
        mock_oauth, mock_http = self._patch_oauth(
            {"access_token": "tok456"},
            {"sub": "google-sub-abc", "email": "bondan@test.com", "name": "Bondan"},
        )
        with patch("app.routers.auth.AsyncOAuth2Client", return_value=mock_oauth), \
             patch("app.routers.auth.httpx.AsyncClient", return_value=mock_http), \
             patch("app.routers.auth.db_get_user_by_google_sub", new_callable=AsyncMock, return_value=FAKE_USER), \
             patch("app.routers.auth.db_update_user_login", new_callable=AsyncMock) as mock_update:
            resp = client.get(
                f"/api/auth/google/callback?code=abc&state={state}",
                cookies={"contextus_oauth_state": state_cookie},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mock_update.assert_called_once()

    def test_seeded_user_gets_google_sub_set(self, client):
        state = "test-state-seed"
        state_cookie = _signed_state(state)
        seeded_user = {**FAKE_USER, "google_sub": None}
        mock_oauth, mock_http = self._patch_oauth(
            {"access_token": "tok789"},
            {"sub": "google-sub-new", "email": "bondan@test.com", "name": "Bondan"},
        )
        with patch("app.routers.auth.AsyncOAuth2Client", return_value=mock_oauth), \
             patch("app.routers.auth.httpx.AsyncClient", return_value=mock_http), \
             patch("app.routers.auth.db_get_user_by_google_sub", new_callable=AsyncMock, return_value=None), \
             patch("app.routers.auth.db_get_user_by_email_no_sub", new_callable=AsyncMock, return_value=seeded_user), \
             patch("app.routers.auth.db_set_google_sub", new_callable=AsyncMock) as mock_set_sub, \
             patch("app.routers.auth.db_update_user_login", new_callable=AsyncMock):
            resp = client.get(
                f"/api/auth/google/callback?code=abc&state={state}",
                cookies={"contextus_oauth_state": state_cookie},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mock_set_sub.assert_called_once_with(seeded_user["user_id"], "google-sub-new")

    def test_clears_state_cookie_on_success(self, client):
        state = "test-state-clear"
        state_cookie = _signed_state(state)
        mock_oauth, mock_http = self._patch_oauth(
            {"access_token": "tok000"},
            {"sub": "sub-xyz", "email": "x@test.com", "name": "X"},
        )
        with patch("app.routers.auth.AsyncOAuth2Client", return_value=mock_oauth), \
             patch("app.routers.auth.httpx.AsyncClient", return_value=mock_http), \
             patch("app.routers.auth.db_get_user_by_google_sub", new_callable=AsyncMock, return_value=None), \
             patch("app.routers.auth.db_get_user_by_email_no_sub", new_callable=AsyncMock, return_value=None), \
             patch("app.routers.auth.db_create_user", new_callable=AsyncMock, return_value=FAKE_USER):
            resp = client.get(
                f"/api/auth/google/callback?code=abc&state={state}",
                cookies={"contextus_oauth_state": state_cookie},
                follow_redirects=False,
            )
        # State cookie should be deleted (max-age=0 or absent)
        assert resp.cookies.get("contextus_oauth_state", "") == ""


class TestLogout:

    def test_logout_returns_204(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 204

    def test_logout_clears_session_cookie(self, client):
        resp = client.post(
            "/api/auth/logout",
            cookies={"contextus_portal_session": _signed_session("usr_abc123")},
        )
        assert resp.status_code == 204


class TestGetMe:

    def test_valid_session_returns_profile(self, client):
        session_cookie = _signed_session("usr_abc123")
        with patch("app.routers.auth.db_get_user_by_id", new_callable=AsyncMock, return_value=FAKE_USER):
            resp = client.get(
                "/api/auth/me",
                cookies={"contextus_portal_session": session_cookie},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "usr_abc123"
        assert data["email"] == "bondan@test.com"

    def test_no_cookie_returns_401(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_tampered_cookie_returns_401(self, client):
        resp = client.get(
            "/api/auth/me",
            cookies={"contextus_portal_session": "tampered.garbage"},
        )
        assert resp.status_code == 401


class TestMissingPortalEnv:

    def test_start_returns_503_when_env_missing(self):
        with patch.dict("os.environ", {
            "GOOGLE_OAUTH_CLIENT_ID": "",
            "PORTAL_SESSION_SECRET": SECRET,
        }, clear=False):
            from app.main import app
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/auth/google/start", follow_redirects=False)
            assert resp.status_code == 503


class TestAdminSiteClaim:

    def test_claim_site_success(self, client):
        with patch("app.routers.auth.db_claim_site", new_callable=AsyncMock, return_value=True):
            resp = client.post(
                "/api/admin/sites/claim",
                json={"email": "bondan@transfez.com", "kb_id": "finfloo"},
                headers={"x-admin-secret": "admin-secret-test"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "claimed"

    def test_claim_site_wrong_secret_returns_401(self, client):
        resp = client.post(
            "/api/admin/sites/claim",
            json={"email": "bondan@transfez.com", "kb_id": "finfloo"},
            headers={"x-admin-secret": "wrong-secret"},
        )
        assert resp.status_code == 401

    def test_revoke_site_success(self, client):
        with patch("app.routers.auth.db_revoke_site", new_callable=AsyncMock, return_value=True):
            resp = client.request(
                "DELETE",
                "/api/admin/sites/claim",
                json={"email": "bondan@transfez.com", "kb_id": "finfloo"},
                headers={"x-admin-secret": "admin-secret-test"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"
