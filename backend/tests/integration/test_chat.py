import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import time
import json

from app.main import app
from app.models import KnowledgeBase, CompanyProfile, Session, Message

client = TestClient(app)


def make_kb(status="complete", has_profile=True):
    return KnowledgeBase(
        job_id="test_job",
        status=status,
        progress="Testing...",
        created_at=int(time.time()),
        company_profile=CompanyProfile(
            name="Test", industry="Tech", services=["tests"], summary="test", gaps=[]
        )
        if has_profile and status == "complete"
        else None,
        chunks=[],
    )


def make_session(messages=0):
    msgs = []
    for _ in range(messages):
        msgs.append(Message(role="user", text="hello", timestamp=int(time.time())))
        msgs.append(Message(role="assistant", text="hi", timestamp=int(time.time())))
    return Session(
        session_id="test_session",
        kb_id="test_job",
        messages=msgs,
        contact_captured=False,
        created_at=int(time.time()),
    )


# Async generator mock for stream_chat_response
async def mock_stream(*args, **kwargs):
    yield "Hello"
    yield " World"


@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.chat.save_session", new_callable=AsyncMock)
@patch("app.routers.chat.archive_session", new_callable=AsyncMock)
@patch("app.routers.chat.stream_chat_response")
@patch("app.routers.chat.redis.get", new_callable=AsyncMock)
def test_chat_valid_message(mock_redis_get, mock_stream_res, mock_archive, mock_save, mock_get_kb, mock_get_session):
    mock_get_session.return_value = make_session()
    mock_get_kb.return_value = make_kb()
    mock_redis_get.return_value = None  # no waitlist prefill

    mock_stream_res.side_effect = mock_stream

    response = client.post("/api/chat/test_session", json={"message": "What services?"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    lines = [line for line in response.text.split("\n\n") if line.strip()]

    # 2 tokens + 1 done signal
    assert len(lines) == 3
    assert 'data: {"token": "Hello"}' in lines[0]
    assert 'data: {"token": " World"}' in lines[1]
    assert 'data: {"done": true, "full_text": "Hello World"}' in lines[2]


@patch("app.routers.chat.get_session", new_callable=AsyncMock)
def test_chat_session_not_found(mock_get_session):
    mock_get_session.return_value = None
    response = client.post("/api/chat/invalid", json={"message": "test"})
    assert response.status_code == 404


@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
def test_chat_kb_not_found(mock_get_kb, mock_get_session):
    mock_get_session.return_value = make_session()
    mock_get_kb.return_value = None
    response = client.post("/api/chat/test_session", json={"message": "test"})
    assert response.status_code == 404


@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
def test_chat_kb_no_profile(mock_get_kb, mock_get_session):
    mock_get_session.return_value = make_session()
    mock_get_kb.return_value = make_kb(has_profile=False)
    response = client.post("/api/chat/test_session", json={"message": "test"})
    assert response.status_code == 400
    assert "no company profile" in response.json()["detail"].lower()


@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
def test_chat_message_limit_exceeded(mock_get_kb, mock_get_session):
    mock_get_session.return_value = make_session(messages=30)  # 30 turns = 60 messages
    mock_get_kb.return_value = make_kb()
    response = client.post("/api/chat/test_session", json={"message": "test"})
    assert response.status_code == 429
    assert "limit reached" in response.json()["detail"].lower()


@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.chat.save_session", new_callable=AsyncMock)
@patch("app.routers.chat.archive_session", new_callable=AsyncMock)
@patch("app.routers.chat.stream_chat_response")
@patch("app.routers.chat.redis.get", new_callable=AsyncMock)
def test_chat_message_limit_ok(mock_redis_get, mock_stream, mock_archive, mock_save, mock_get_kb, mock_get_session):
    mock_get_session.return_value = make_session(messages=29)
    mock_get_kb.return_value = make_kb()
    mock_redis_get.return_value = None  # no waitlist prefill

    async def mock_gen(*args, **kwargs):
        yield "Hi"

    mock_stream.side_effect = mock_gen

    response = client.post("/api/chat/test_session", json={"message": "test"})
    assert response.status_code == 200


# -----------------
# Contact Detection
# -----------------
def test_chat_detect_email():
    from app.routers.chat import detect_contact

    contact = detect_contact("Email me at test@example.com please")
    assert contact["email"] == "test@example.com"


def test_chat_detect_email_multiple():
    from app.routers.chat import detect_contact

    contact = detect_contact("Emails: a@example.com and b@example.com")
    assert contact["email"] == "a@example.com"


def test_chat_detect_phone_indo_08():
    from app.routers.chat import detect_contact

    contact = detect_contact("Call 08123456789")
    assert contact["phone"] == "08123456789"


def test_chat_detect_phone_indo_62():
    from app.routers.chat import detect_contact

    contact = detect_contact("Call +62812345678")
    assert contact["phone"] == "+62812345678"


def test_chat_detect_whatsapp_wa_me():
    from app.routers.chat import detect_contact

    contact = detect_contact("wa.me/62812345678")
    assert contact["whatsapp"] == "wa.me/62812345678"


def test_chat_detect_whatsapp_url():
    from app.routers.chat import detect_contact

    contact = detect_contact("whatsapp.com/send?phone=something")
    assert contact["whatsapp"] == "whatsapp.com"  # Matching the domain


def test_chat_no_contact():
    from app.routers.chat import detect_contact

    contact = detect_contact("What are your hours?")
    assert contact is None


# -----------------
# Persistence tests
# -----------------
@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.chat.save_session", new_callable=AsyncMock)
@patch("app.routers.chat.archive_session", new_callable=AsyncMock)
@patch("app.routers.chat.stream_chat_response")
@patch("app.routers.chat.redis.get", new_callable=AsyncMock)
def test_chat_saves_user_and_assistant_message(
    mock_redis_get, mock_stream, mock_archive, mock_save, mock_get_kb, mock_get_session
):
    s = make_session(messages=0)
    mock_get_session.return_value = s
    mock_get_kb.return_value = make_kb()
    mock_redis_get.return_value = None  # no waitlist prefill

    async def mock_gen(*args, **kwargs):
        yield "Answer"

    mock_stream.side_effect = mock_gen

    # We must consume the stream to actually reach the save logic (it is inside a generator in fastapi)
    response = client.post("/api/chat/test_session", json={"message": "Question"})
    text = response.text

    # `mock_save` is called inside the `generate()` response chunking loop, since FastAPI evaluates generators dynamically.
    # We've verified string outputs, let's verify mock calls from the background loop
    assert mock_save.called
    saved_session = mock_save.call_args[0][1]

    # 0 -> Question, 1 -> Answer
    assert len(saved_session.messages) == 2
    assert saved_session.messages[0].role == "user"
    assert saved_session.messages[0].text == "Question"
    assert saved_session.messages[1].role == "assistant"
    assert saved_session.messages[1].text == "Answer"


# SSE formats are covered by test_chat_valid_message checking the line structure.


# -----------------
# Archive tests
# -----------------
@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.chat.save_session", new_callable=AsyncMock)
@patch("app.routers.chat.archive_session", new_callable=AsyncMock)
@patch("app.routers.chat.stream_chat_response")
@patch("app.routers.chat.redis.get", new_callable=AsyncMock)
def test_archive_session_called_after_message(
    mock_redis_get, mock_stream, mock_archive, mock_save, mock_get_kb, mock_get_session
):
    s = make_session(messages=0)
    mock_get_session.return_value = s
    mock_get_kb.return_value = make_kb()
    mock_redis_get.return_value = None

    async def mock_gen(*args, **kwargs):
        yield "Answer"

    mock_stream.side_effect = mock_gen

    client.post("/api/chat/test_session", json={"message": "Hello"})

    assert mock_archive.called
    archived = mock_archive.call_args[0][0]
    assert archived.session_id == "test_session"
    assert len(archived.messages) == 2


@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.chat.save_session", new_callable=AsyncMock)
@patch("app.routers.chat.archive_session", new_callable=AsyncMock)
@patch("app.routers.chat.stream_chat_response")
@patch("app.routers.chat.redis.get", new_callable=AsyncMock)
def test_archive_session_called_once_per_turn(
    mock_redis_get, mock_stream, mock_archive, mock_save, mock_get_kb, mock_get_session
):
    mock_get_session.return_value = make_session(messages=2)
    mock_get_kb.return_value = make_kb()
    mock_redis_get.return_value = None

    async def mock_gen(*args, **kwargs):
        yield "Reply"

    mock_stream.side_effect = mock_gen

    client.post("/api/chat/test_session", json={"message": "Another turn"})

    assert mock_archive.call_count == 1


@patch("app.routers.chat.get_session", new_callable=AsyncMock)
@patch("app.routers.chat.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.chat.save_session", new_callable=AsyncMock)
@patch("app.routers.chat.archive_session", new_callable=AsyncMock)
@patch("app.routers.chat.stream_chat_response")
@patch("app.routers.chat.redis.get", new_callable=AsyncMock)
def test_archive_session_receives_updated_session(
    mock_redis_get, mock_stream, mock_archive, mock_save, mock_get_kb, mock_get_session
):
    """archive_session should receive the session with contact_captured=True when contact is detected."""
    s = make_session(messages=0)
    mock_get_session.return_value = s
    mock_get_kb.return_value = make_kb()
    mock_redis_get.return_value = None

    async def mock_gen(*args, **kwargs):
        yield "Got it"

    mock_stream.side_effect = mock_gen

    with patch("app.routers.chat.extend_session_ttl", new_callable=AsyncMock):
        client.post("/api/chat/test_session", json={"message": "Email me at user@example.com"})

    archived = mock_archive.call_args[0][0]
    assert archived.contact_captured is True
    assert "user@example.com" in archived.contact_value
