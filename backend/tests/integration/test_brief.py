import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
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

def mock_lead_brief():
    return LeadBrief(
        session_id="test_session",
        created_at=str(time.time()),
        who="tester",
        need="api testing",
        signals="urgency",
        open_questions="budget?",
        suggested_approach="email",
        quality_score="high",
        metadata={"tokens": 100}
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
