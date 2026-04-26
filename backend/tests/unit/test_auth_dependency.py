"""
Unit tests for get_current_user and get_current_user_for_kb FastAPI dependencies.
No HTTP layer, no real DB — all mocked.
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer

SECRET = "test-secret-for-unit-tests"
FAKE_USER = {
    "user_id": "usr_abc123",
    "email": "bondan@test.com",
    "display_name": "Bondan",
    "google_sub": "google-sub-abc",
    "created_at": 1000000,
    "last_login_at": 1000001,
}


def _make_signed_cookie(payload: dict, secret: str = SECRET) -> str:
    return URLSafeTimedSerializer(secret).dumps(payload)


def _make_request(cookie_value: str | None):
    class FakeRequest:
        cookies = {k: v for k, v in [("contextus_portal_session", cookie_value)] if v is not None}
    return FakeRequest()


class TestGetCurrentUser:

    @pytest.mark.asyncio
    async def test_valid_cookie_returns_user(self):
        cookie = _make_signed_cookie({"user_id": "usr_abc123"})
        request = _make_request(cookie)
        with patch("app.routers.auth._serializer") as mock_ser, \
             patch("app.routers.auth.db_get_user_by_id", new_callable=AsyncMock) as mock_db, \
             patch.dict("os.environ", {"PORTAL_SESSION_SECRET": SECRET}):
            mock_ser.return_value = URLSafeTimedSerializer(SECRET)
            mock_db.return_value = FAKE_USER
            from app.routers.auth import get_current_user
            user = await get_current_user(request)
            assert user["user_id"] == "usr_abc123"

    @pytest.mark.asyncio
    async def test_missing_cookie_raises_401(self):
        request = _make_request(None)
        with patch.dict("os.environ", {"PORTAL_SESSION_SECRET": SECRET}):
            from app.routers.auth import get_current_user
            with pytest.raises(HTTPException) as exc:
                await get_current_user(request)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_tampered_cookie_raises_401(self):
        request = _make_request("not.a.valid.signed.cookie")
        with patch("app.routers.auth._serializer") as mock_ser, \
             patch.dict("os.environ", {"PORTAL_SESSION_SECRET": SECRET}):
            mock_ser.return_value = URLSafeTimedSerializer(SECRET)
            from app.routers.auth import get_current_user
            with pytest.raises(HTTPException) as exc:
                await get_current_user(request)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_cookie_raises_401(self):
        from itsdangerous import SignatureExpired
        cookie = _make_signed_cookie({"user_id": "usr_abc123"})
        request = _make_request(cookie)
        with patch("app.routers.auth._serializer") as mock_ser, \
             patch.dict("os.environ", {"PORTAL_SESSION_SECRET": SECRET}):
            ser = URLSafeTimedSerializer(SECRET)
            ser.loads = lambda *a, **kw: (_ for _ in ()).throw(SignatureExpired("expired"))
            mock_ser.return_value = ser
            from app.routers.auth import get_current_user
            with pytest.raises(HTTPException) as exc:
                await get_current_user(request)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_in_db_raises_401(self):
        cookie = _make_signed_cookie({"user_id": "usr_abc123"})
        request = _make_request(cookie)
        with patch("app.routers.auth._serializer") as mock_ser, \
             patch("app.routers.auth.db_get_user_by_id", new_callable=AsyncMock) as mock_db, \
             patch.dict("os.environ", {"PORTAL_SESSION_SECRET": SECRET}):
            mock_ser.return_value = URLSafeTimedSerializer(SECRET)
            mock_db.return_value = None
            from app.routers.auth import get_current_user
            with pytest.raises(HTTPException) as exc:
                await get_current_user(request)
            assert exc.value.status_code == 401


class TestGetCurrentUserForKb:

    @pytest.mark.asyncio
    async def test_user_with_access_passes(self):
        with patch("app.routers.auth.db_user_has_kb_access", new_callable=AsyncMock) as mock_access:
            mock_access.return_value = True
            from app.routers.auth import get_current_user_for_kb
            await get_current_user_for_kb(kb_id="kb_finfloo", user=FAKE_USER)
            mock_access.assert_called_once_with("usr_abc123", "kb_finfloo")

    @pytest.mark.asyncio
    async def test_user_without_access_raises_403(self):
        with patch("app.routers.auth.db_user_has_kb_access", new_callable=AsyncMock) as mock_access:
            mock_access.return_value = False
            from app.routers.auth import get_current_user_for_kb
            with pytest.raises(HTTPException) as exc:
                await get_current_user_for_kb(kb_id="kb_finfloo", user=FAKE_USER)
            assert exc.value.status_code == 403
