import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Session, Message


def make_session(n_turns=1):
    msgs = []
    for i in range(n_turns):
        msgs.append(Message(role="user", text=f"q{i}", timestamp=int(time.time())))
        msgs.append(Message(role="assistant", text=f"a{i}", timestamp=int(time.time())))
    return Session(
        session_id="sess_abc",
        kb_id="kb_xyz",
        messages=msgs,
        contact_captured=False,
        created_at=int(time.time()),
    )


@pytest.mark.asyncio
async def test_archive_session_skips_when_no_database_url():
    from app.services import database as db_module
    original = db_module.DATABASE_URL
    db_module.DATABASE_URL = ""
    try:
        from app.services.database import archive_session
        # Should return without error and without touching pool
        with patch.object(db_module, "get_pool", new_callable=AsyncMock) as mock_pool:
            await archive_session(make_session())
            mock_pool.assert_not_called()
    finally:
        db_module.DATABASE_URL = original


@pytest.mark.asyncio
async def test_archive_session_upserts_correct_fields():
    from app.services import database as db_module

    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db_module, "DATABASE_URL", "postgresql://fake"), \
         patch.object(db_module, "get_pool", AsyncMock(return_value=mock_pool)):
        from app.services.database import archive_session
        session = make_session(n_turns=2)
        session.contact_captured = True
        session.contact_value = '{"email": "a@b.com"}'
        await archive_session(session)

    mock_conn.execute.assert_called_once()
    args = mock_conn.execute.call_args[0]

    # positional params: session_id, kb_id, messages_json, message_count, contact_captured, contact_value, brief_sent, created_at
    assert args[1] == "sess_abc"
    assert args[2] == "kb_xyz"
    messages = json.loads(args[3])
    assert len(messages) == 4
    assert args[4] == 4       # message_count
    assert args[5] is True    # contact_captured
    assert args[6] == '{"email": "a@b.com"}'
    assert args[7] is False   # brief_sent


@pytest.mark.asyncio
async def test_archive_session_swallows_db_error(caplog):
    from app.services import database as db_module

    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = Exception("connection refused")
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db_module, "DATABASE_URL", "postgresql://fake"), \
         patch.object(db_module, "get_pool", AsyncMock(return_value=mock_pool)):
        from app.services.database import archive_session
        # Must not raise — errors are logged, not propagated
        await archive_session(make_session())

    assert any("archive_session" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_db_mark_brief_sent_updates_row():
    from app.services import database as db_module

    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db_module, "DATABASE_URL", "postgresql://fake"), \
         patch.object(db_module, "get_pool", AsyncMock(return_value=mock_pool)):
        from app.services.database import db_mark_brief_sent
        await db_mark_brief_sent("sess_abc")

    mock_conn.execute.assert_called_once()
    sql, session_id = mock_conn.execute.call_args[0]
    assert "brief_sent = true" in sql.lower()
    assert session_id == "sess_abc"


@pytest.mark.asyncio
async def test_db_mark_brief_sent_skips_when_no_database_url():
    from app.services import database as db_module
    original = db_module.DATABASE_URL
    db_module.DATABASE_URL = ""
    try:
        from app.services.database import db_mark_brief_sent
        with patch.object(db_module, "get_pool", new_callable=AsyncMock) as mock_pool:
            await db_mark_brief_sent("sess_abc")
            mock_pool.assert_not_called()
    finally:
        db_module.DATABASE_URL = original
