import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock, call
import time

from app.main import app
from app.models import KnowledgeBase, CompanyProfile, Session, Message, LeadBrief

client = TestClient(app)

def make_kb(status="complete"):
    return KnowledgeBase(
        job_id="test_job",
        status=status,
        progress="Testing...",
        created_at=int(time.time()),
        company_profile=CompanyProfile(
            name="Test", 
            industry="Tech", 
            services=["tests"], 
            summary="test", 
            gaps=[]
        ) if status == "complete" else None,
        chunks=[]
    )

def make_session(messages=4, has_contact=False):
    msgs = []
    # add `messages` number of messages
    for i in range(messages):
        msgs.append(Message(role="user" if i % 2 == 0 else "assistant", text=f"msg {i}", timestamp=int(time.time())))
        
    return Session(
        session_id="test_session",
        kb_id="test_job",
        messages=msgs,
        contact_captured=has_contact,
        contact_value='{"email":"test@test.com"}' if has_contact else None,
        created_at=int(time.time())
    )

def mock_lead_brief(with_contact=False):
    return LeadBrief(
        session_id="test_session",
        created_at=str(int(time.time())),
        who="tester",
        need="api testing",
        signals="urgency",
        open_questions="budget?",
        suggested_approach="email",
        quality_score="high",
        contact={"email": "test@test.com", "phone": None, "whatsapp": None} if with_contact else None,
        metadata={"model": "anthropic/claude-sonnet-4"}
    )

@patch("app.routers.brief.get_session", new_callable=AsyncMock)
@patch("app.routers.brief.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.brief.generate_lead_brief")
def test_brief_valid(mock_generate, mock_get_kb, mock_get_session):
    mock_get_session.return_value = make_session(messages=4)
    mock_get_kb.return_value = make_kb()
    mock_generate.return_value = mock_lead_brief()
    
    response = client.post("/api/brief/test_session")
    assert response.status_code == 200
    data = response.json()
    assert data["who"] == "tester"
    assert data["quality_score"] in ["high", "medium", "low"]
    assert data["session_id"] == "test_session"

@patch("app.routers.brief.get_session", new_callable=AsyncMock)
@patch("app.routers.brief.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.brief.generate_lead_brief")
def test_brief_minimum_messages(mock_generate, mock_get_kb, mock_get_session):
    mock_get_session.return_value = make_session(messages=2)
    mock_get_kb.return_value = make_kb()
    mock_generate.return_value = mock_lead_brief()
    
    response = client.post("/api/brief/test_session")
    assert response.status_code == 200

@patch("app.routers.brief.get_session", new_callable=AsyncMock)
def test_brief_insufficient_messages(mock_get_session):
    mock_get_session.return_value = make_session(messages=1)
    response = client.post("/api/brief/test_session")
    assert response.status_code == 400
    assert "at least 2 messages" in response.json()["detail"].lower()

@patch("app.routers.brief.get_session", new_callable=AsyncMock)
def test_brief_empty_session(mock_get_session):
    mock_get_session.return_value = make_session(messages=0)
    response = client.post("/api/brief/test_session")
    assert response.status_code == 400

@patch("app.routers.brief.get_session", new_callable=AsyncMock)
def test_brief_session_not_found(mock_get_session):
    mock_get_session.return_value = None
    response = client.post("/api/brief/invalid")
    assert response.status_code == 404

@patch("app.routers.brief.get_session", new_callable=AsyncMock)
@patch("app.routers.brief.get_knowledge_base", new_callable=AsyncMock)
def test_brief_kb_not_found(mock_get_kb, mock_get_session):
    mock_get_session.return_value = make_session(messages=4)
    mock_get_kb.return_value = None
    response = client.post("/api/brief/test_session")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Webhook tests
# ---------------------------------------------------------------------------

WEBHOOK_URL = "https://hooks.example.com/lead"


@patch("app.routers.brief.asyncio.create_task")
@patch("app.routers.brief.fire_webhook", new_callable=AsyncMock)
@patch("app.routers.brief.get_customer_config", new_callable=AsyncMock)
@patch("app.routers.brief.generate_lead_brief", new_callable=AsyncMock)
@patch("app.routers.brief.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.brief.get_session", new_callable=AsyncMock)
def test_webhook_fired_when_url_configured(
    mock_get_session, mock_get_kb, mock_generate, mock_get_config, mock_fire, mock_create_task
):
    mock_get_session.return_value = make_session(messages=4)
    mock_get_kb.return_value = make_kb()
    mock_generate.return_value = mock_lead_brief()
    mock_get_config.return_value = {"webhook_url": WEBHOOK_URL}

    response = client.post("/api/brief/test_session")
    assert response.status_code == 200
    mock_fire.assert_called_once_with(WEBHOOK_URL, mock_generate.return_value)
    mock_create_task.assert_called_once()


@patch("app.routers.brief.asyncio.create_task")
@patch("app.routers.brief.get_customer_config", new_callable=AsyncMock)
@patch("app.routers.brief.generate_lead_brief", new_callable=AsyncMock)
@patch("app.routers.brief.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.brief.get_session", new_callable=AsyncMock)
def test_webhook_not_fired_when_no_url(
    mock_get_session, mock_get_kb, mock_generate, mock_get_config, mock_create_task
):
    mock_get_session.return_value = make_session(messages=4)
    mock_get_kb.return_value = make_kb()
    mock_generate.return_value = mock_lead_brief()
    mock_get_config.return_value = {"webhook_url": None}

    response = client.post("/api/brief/test_session")
    assert response.status_code == 200
    mock_create_task.assert_not_called()


@patch("app.routers.brief.asyncio.create_task")
@patch("app.routers.brief.get_customer_config", new_callable=AsyncMock)
@patch("app.routers.brief.generate_lead_brief", new_callable=AsyncMock)
@patch("app.routers.brief.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.brief.get_session", new_callable=AsyncMock)
def test_webhook_not_fired_when_no_config(
    mock_get_session, mock_get_kb, mock_generate, mock_get_config, mock_create_task
):
    mock_get_session.return_value = make_session(messages=4)
    mock_get_kb.return_value = make_kb()
    mock_generate.return_value = mock_lead_brief()
    mock_get_config.return_value = None

    response = client.post("/api/brief/test_session")
    assert response.status_code == 200
    mock_create_task.assert_not_called()


@patch("app.routers.brief.asyncio.create_task")
@patch("app.routers.brief.fire_webhook", new_callable=AsyncMock)
@patch("app.routers.brief.get_customer_config", new_callable=AsyncMock)
@patch("app.routers.brief.generate_lead_brief", new_callable=AsyncMock)
@patch("app.routers.brief.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.brief.get_session", new_callable=AsyncMock)
def test_webhook_payload_shape(
    mock_get_session, mock_get_kb, mock_generate, mock_get_config, mock_fire, mock_create_task
):
    """Payload sent to webhook matches the expected key/value structure."""
    mock_get_session.return_value = make_session(messages=4, has_contact=True)
    mock_get_kb.return_value = make_kb()
    brief = mock_lead_brief(with_contact=True)
    mock_generate.return_value = brief
    mock_get_config.return_value = {"webhook_url": WEBHOOK_URL}

    response = client.post("/api/brief/test_session")
    assert response.status_code == 200

    # Capture the LeadBrief passed to fire_webhook
    fired_brief: LeadBrief = mock_fire.call_args[0][1]
    payload = fired_brief.model_dump()

    # All required top-level keys must be present
    required_keys = {
        "session_id", "created_at", "who", "need",
        "signals", "open_questions", "suggested_approach",
        "quality_score", "contact", "metadata",
    }
    assert required_keys == set(payload.keys())

    # Quality score is one of the three valid values
    assert payload["quality_score"] in ("high", "medium", "low")

    # contact has exactly email / phone / whatsapp keys (not null dict)
    contact = payload["contact"]
    assert contact is not None
    assert set(contact.keys()) == {"email", "phone", "whatsapp"}

    # metadata always present and non-empty
    assert isinstance(payload["metadata"], dict)
    assert payload["metadata"]
