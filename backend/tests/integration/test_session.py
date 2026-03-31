import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import time

from app.main import app
from app.models import KnowledgeBase, CompanyProfile, Session, Message

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

def make_session(has_contact=False, messages=0):
    msgs = []
    for i in range(messages):
        msgs.append(Message(role="user", text="hello", timestamp=int(time.time())))
    
    return Session(
        session_id="test_session",
        kb_id="test_job",
        messages=msgs,
        contact_captured=has_contact,
        contact_value="test@test.com" if has_contact else None,
        created_at=int(time.time())
    )

# POST /api/session
@patch("app.routers.session.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.session.save_session", new_callable=AsyncMock)
def test_create_session_valid(mock_save, mock_get_kb):
    mock_get_kb.return_value = make_kb("complete")
    response = client.post("/api/session", json={"knowledge_base_id": "test_job"})
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert mock_save.called

@patch("app.routers.session.get_knowledge_base", new_callable=AsyncMock)
def test_create_session_kb_not_found(mock_get_kb):
    mock_get_kb.return_value = None
    response = client.post("/api/session", json={"knowledge_base_id": "invalid"})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

@patch("app.routers.session.get_knowledge_base", new_callable=AsyncMock)
def test_create_session_kb_not_ready(mock_get_kb):
    mock_get_kb.return_value = make_kb("crawling")
    response = client.post("/api/session", json={"knowledge_base_id": "test_job"})
    assert response.status_code == 400
    assert "not ready" in response.json()["detail"].lower()

@patch("app.routers.session.get_knowledge_base", new_callable=AsyncMock)
def test_create_session_kb_failed(mock_get_kb):
    mock_get_kb.return_value = make_kb("failed")
    response = client.post("/api/session", json={"knowledge_base_id": "test_job"})
    assert response.status_code == 400
    assert "not ready" in response.json()["detail"].lower()

@patch("app.routers.session.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.session.save_session", new_callable=AsyncMock)
def test_create_session_saves_to_redis(mock_save_session, mock_get_kb):
    mock_get_kb.return_value = make_kb("complete")
    response = client.post("/api/session", json={"knowledge_base_id": "test_job"})
    assert response.status_code == 200
    assert mock_save_session.called
    saved_session = mock_save_session.call_args[0][1]
    assert saved_session.kb_id == "test_job"
    assert saved_session.messages == []

# GET /api/session/{session_id}
@patch("app.routers.session.get_session", new_callable=AsyncMock)
def test_get_session_valid(mock_get_session):
    mock_get_session.return_value = make_session()
    response = client.get("/api/session/test_session")
    assert response.status_code == 200
    assert response.json()["session_id"] == "test_session"

@patch("app.routers.session.get_session", new_callable=AsyncMock)
def test_get_session_not_found(mock_get_session):
    mock_get_session.return_value = None
    response = client.get("/api/session/invalid")
    assert response.status_code == 404

@patch("app.routers.session.get_session", new_callable=AsyncMock)
def test_get_session_with_messages(mock_get_session):
    mock_get_session.return_value = make_session(messages=3)
    response = client.get("/api/session/test_session")
    assert response.status_code == 200
    assert len(response.json()["messages"]) == 3

@patch("app.routers.session.get_session", new_callable=AsyncMock)
def test_get_session_with_contact(mock_get_session):
    mock_get_session.return_value = make_session(has_contact=True)
    response = client.get("/api/session/test_session")
    assert response.status_code == 200
    assert response.json()["contact_captured"] is True
    assert response.json()["contact_value"] == "test@test.com"
