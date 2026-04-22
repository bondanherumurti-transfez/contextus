import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import time

from app.main import app
from app.models import KnowledgeBase, CompanyProfile
from app.services.crawler import validate_url

client = TestClient(app)

# Helper for KnowledgeBase factory
def make_kb(status="crawling"):
    return KnowledgeBase(
        job_id="test_job_123",
        status=status,
        progress="Testing...",
        created_at=int(time.time()),
        company_profile=CompanyProfile(
            name="Test", 
            industry="Tech", 
            services=["test svc"], 
            summary="Test summary", 
            gaps=[]
        ) if status == "complete" else None,
        chunks=[]
    )

# ---------------------------------------------------------
# Tests for POST /api/crawl
# ---------------------------------------------------------

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
def test_start_crawl_valid_url(mock_save, mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={"url": "https://example.com"})
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "crawling"

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_invalid_protocol(mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={"url": "ftp://example.com"})
    assert response.status_code == 400

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_missing_url(mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={})
    assert response.status_code == 422  # Validation error

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_empty_url(mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={"url": ""})
    assert response.status_code == 400

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_localhost(mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={"url": "http://localhost:3000"})
    assert response.status_code == 400

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_127_0_0_1(mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={"url": "http://127.0.0.1"})
    assert response.status_code == 400

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_private_ip_192(mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={"url": "http://192.168.1.1"})
    assert response.status_code == 400

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_private_ip_10(mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={"url": "http://10.0.0.1"})
    assert response.status_code == 400

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
def test_start_crawl_rate_limit_exceeded(mock_rate_limit):
    mock_rate_limit.return_value = False
    response = client.post("/api/crawl", json={"url": "https://example.com"})
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]

@patch("app.routers.crawl.check_rate_limit", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
def test_start_crawl_creates_kb_in_redis(mock_save, mock_rate_limit):
    mock_rate_limit.return_value = True
    response = client.post("/api/crawl", json={"url": "https://example.com"})
    assert response.status_code == 200
    assert mock_save.called
    kb_arg = mock_save.call_args[0][1]
    assert kb_arg.status == "crawling"

# ---------------------------------------------------------
# Tests for GET /api/crawl/{job_id}
# ---------------------------------------------------------

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_get_crawl_status_not_found(mock_get_kb):
    mock_get_kb.return_value = None
    response = client.get("/api/crawl/invalid_job_id")
    assert response.status_code == 404

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_get_crawl_status_crawling(mock_get_kb):
    mock_get_kb.return_value = make_kb(status="crawling")
    response = client.get("/api/crawl/test_job_123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "crawling"
    assert "progress" in data

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_get_crawl_status_complete(mock_get_kb):
    mock_get_kb.return_value = make_kb(status="complete")
    response = client.get("/api/crawl/test_job_123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert "company_profile" in data
    assert "chunks" in data

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_get_crawl_status_failed(mock_get_kb):
    kb = make_kb(status="failed")
    kb.progress = "Timed out"
    mock_get_kb.return_value = kb
    response = client.get("/api/crawl/test_job_123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["progress"] == "Timed out"

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_get_crawl_status_returns_full_kb(mock_get_kb):
    mock_get_kb.return_value = make_kb(status="complete")
    response = client.get("/api/crawl/test_job_123")
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "created_at" in data

# ---------------------------------------------------------
# Tests for POST /api/crawl/{job_id}/enrich
# ---------------------------------------------------------

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.generate_company_profile")
def test_enrich_valid(mock_generate_profile, mock_save, mock_get_kb):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_generate_profile.return_value = CompanyProfile(
        name="Enriched", 
        industry="Tech", 
        services=["widgets"], 
        summary="Updated", 
        gaps=[]
    )
    
    response = client.post("/api/crawl/test_job_123/enrich", json={
        "answers": {"services": "We sell widgets"}
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Enriched"

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_enrich_not_found(mock_get_kb):
    mock_get_kb.return_value = None
    response = client.post("/api/crawl/invalid_job_123/enrich", json={"answers": {}})
    assert response.status_code == 404

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_enrich_job_not_complete(mock_get_kb):
    mock_get_kb.return_value = make_kb(status="crawling")
    response = client.post("/api/crawl/invalid_job_123/enrich", json={"answers": {}})
    assert response.status_code == 400
    assert "not complete" in response.json()["detail"]

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
def test_enrich_empty_answers(mock_save, mock_get_kb):
    kb = make_kb(status="complete")
    mock_get_kb.return_value = kb
    
    response = client.post("/api/crawl/test_job_123/enrich", json={"answers": {}})
    assert response.status_code == 200
    # verify chunks are not added
    assert len(kb.chunks) == 0

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.generate_company_profile")
@patch("app.routers.crawl.assess_quality_tier")
def test_enrich_adds_chunks(mock_assess, mock_generate, mock_save, mock_get_kb):
    kb = make_kb(status="complete")
    mock_get_kb.return_value = kb
    mock_generate.return_value = CompanyProfile(
        name="Enriched", 
        industry="Tech", 
        services=["widgets"], 
        summary="Updated", 
        gaps=[]
    )
    
    response = client.post("/api/crawl/test_job_123/enrich", json={
        "answers": {"services": "We sell widgets"}
    })
    assert response.status_code == 200
    assert len(kb.chunks) == 1
    assert kb.chunks[0].source == "interview:services"

@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.generate_company_profile")
@patch("app.routers.crawl.assess_quality_tier")
def test_enrich_updates_quality_tier(mock_assess, mock_generate, mock_save, mock_get_kb):
    kb = make_kb(status="complete")
    mock_get_kb.return_value = kb
    mock_assess.return_value = "rich"
    mock_generate.return_value = CompanyProfile(
        name="Enriched",
        industry="Tech",
        services=["widgets"],
        summary="Updated",
        gaps=[]
    )

    response = client.post("/api/crawl/test_job_123/enrich", json={
        "answers": {"services": "We sell widgets"}
    })
    assert response.status_code == 200
    assert kb.quality_tier == "rich"


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.generate_company_profile")
@patch("app.routers.crawl.assess_quality_tier")
def test_enrich_permanent_kb_requires_admin_secret(mock_assess, mock_generate, mock_save, mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = make_kb(status="complete")  # found in Neon = permanent
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake", "ADMIN_SECRET": "secret123"}):
        response = client.post("/api/crawl/test_job_123/enrich", json={
            "answers": {"services": "We sell widgets"}
        })
    assert response.status_code == 401


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.generate_company_profile")
@patch("app.routers.crawl.assess_quality_tier")
def test_enrich_permanent_kb_valid_admin_secret_saves_to_neon(mock_assess, mock_generate, mock_save, mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = make_kb(status="complete")  # found in Neon = permanent
    mock_assess.return_value = "rich"
    mock_generate.return_value = CompanyProfile(
        name="Enriched", industry="Tech", services=["widgets"], summary="Updated", gaps=[]
    )
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake", "ADMIN_SECRET": "secret123"}):
        response = client.post(
            "/api/crawl/test_job_123/enrich",
            json={"answers": {"services": "We sell widgets"}},
            headers={"x-admin-secret": "secret123"},
        )
    assert response.status_code == 200
    mock_save.assert_awaited_once()
    call_kwargs = mock_save.call_args
    assert call_kwargs.kwargs.get("permanent") is True
    assert call_kwargs.kwargs.get("ttl") is None


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_enrich_db_error_returns_503(mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.side_effect = Exception("Neon connection failed")
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake"}):
        response = client.post("/api/crawl/test_job_123/enrich", json={
            "answers": {"services": "We sell widgets"}
        })
    assert response.status_code == 503
    assert "retry" in response.json()["detail"]


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.generate_company_profile")
@patch("app.routers.crawl.assess_quality_tier")
def test_enrich_ephemeral_kb_saves_to_redis_with_ttl(mock_assess, mock_generate, mock_save, mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = None  # not in Neon = ephemeral
    mock_assess.return_value = "thin"
    mock_generate.return_value = CompanyProfile(
        name="Enriched", industry="Tech", services=["widgets"], summary="Updated", gaps=[]
    )
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake"}):
        response = client.post("/api/crawl/test_job_123/enrich", json={
            "answers": {"services": "We sell widgets"}
        })
    assert response.status_code == 200
    mock_save.assert_awaited_once()
    call_kwargs = mock_save.call_args
    assert call_kwargs.kwargs.get("permanent") is False
    assert call_kwargs.kwargs.get("ttl") == 1800


# ---------------------------------------------------------
# Tests for PATCH /api/crawl/{job_id}/pills
# ---------------------------------------------------------

CUSTOM_PILLS = ["What do you offer?", "What are your prices?", "How do I get started?"]


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
def test_update_pills_valid(mock_save, mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = None  # ephemeral KB — no auth needed
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake"}):
        response = client.patch("/api/crawl/test_job_123/pills", json={"pills": CUSTOM_PILLS})
    assert response.status_code == 200
    data = response.json()
    assert data["suggested_pills"] == CUSTOM_PILLS
    assert data["job_id"] == "test_job_123"


@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_update_pills_not_found(mock_get_kb):
    mock_get_kb.return_value = None
    response = client.patch("/api/crawl/no_such_job/pills", json={"pills": CUSTOM_PILLS})
    assert response.status_code == 404


@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_update_pills_job_not_complete(mock_get_kb):
    mock_get_kb.return_value = make_kb(status="crawling")
    response = client.patch("/api/crawl/test_job_123/pills", json={"pills": CUSTOM_PILLS})
    assert response.status_code == 400
    assert "not complete" in response.json()["detail"]


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_update_pills_too_few(mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = None
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake"}):
        response = client.patch("/api/crawl/test_job_123/pills", json={"pills": ["Only one pill"]})
    assert response.status_code == 400
    assert "3 pills" in response.json()["detail"]


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_update_pills_too_many(mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = None
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake"}):
        response = client.patch("/api/crawl/test_job_123/pills", json={"pills": CUSTOM_PILLS + ["Extra pill"]})
    assert response.status_code == 400
    assert "3 pills" in response.json()["detail"]


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_update_pills_empty_list(mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = None
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake"}):
        response = client.patch("/api/crawl/test_job_123/pills", json={"pills": []})
    assert response.status_code == 400
    assert "3 pills" in response.json()["detail"]


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
def test_update_pills_permanent_kb_requires_admin_secret(mock_save, mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = make_kb(status="complete")  # found in Neon = permanent
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake", "ADMIN_SECRET": "secret123"}):
        response = client.patch("/api/crawl/test_job_123/pills", json={"pills": CUSTOM_PILLS})
    assert response.status_code == 401


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
def test_update_pills_permanent_kb_valid_admin_secret(mock_save, mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = make_kb(status="complete")  # found in Neon = permanent
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake", "ADMIN_SECRET": "secret123"}):
        response = client.patch(
            "/api/crawl/test_job_123/pills",
            json={"pills": CUSTOM_PILLS},
            headers={"x-admin-secret": "secret123"},
        )
    assert response.status_code == 200
    assert response.json()["suggested_pills"] == CUSTOM_PILLS
    mock_save.assert_awaited_once()
    call_kwargs = mock_save.call_args
    assert call_kwargs.kwargs.get("permanent") is True


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.save_knowledge_base", new_callable=AsyncMock)
def test_update_pills_permanent_kb_missing_admin_secret_env(mock_save, mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.return_value = make_kb(status="complete")  # found in Neon = permanent
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake"}, clear=False):
        # Ensure ADMIN_SECRET is unset
        import os
        os.environ.pop("ADMIN_SECRET", None)
        response = client.patch(
            "/api/crawl/test_job_123/pills",
            json={"pills": CUSTOM_PILLS},
            headers={"x-admin-secret": "anything"},
        )
    assert response.status_code == 500
    assert "misconfiguration" in response.json()["detail"]


@patch("app.routers.crawl.db_get_knowledge_base", new_callable=AsyncMock)
@patch("app.routers.crawl.get_knowledge_base", new_callable=AsyncMock)
def test_update_pills_db_error_returns_503(mock_get_kb, mock_db_get):
    mock_get_kb.return_value = make_kb(status="complete")
    mock_db_get.side_effect = Exception("Neon connection failed")
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://fake"}):
        response = client.patch("/api/crawl/test_job_123/pills", json={"pills": CUSTOM_PILLS})
    assert response.status_code == 503
    assert "retry" in response.json()["detail"]
