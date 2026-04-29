"""
Unit tests for enrich_kb() in routers/crawl.py.

Covers the bug where profile regeneration silently wiped custom_instructions
because generate_company_profile returns a fresh CompanyProfile with
custom_instructions=None.
"""
import pytest
from unittest.mock import patch, AsyncMock

from app.models import KnowledgeBase, CompanyProfile


def _make_kb(custom_instructions=None, chunks=None):
    return KnowledgeBase.model_validate({
        "job_id": "kb_finfloo",
        "status": "complete",
        "progress": "",
        "pages_found": 5,
        "quality_tier": "rich",
        "company_profile": {
            "name": "Finfloo",
            "industry": "Accounting",
            "services": ["Bookkeeping"],
            "out_of_scope": [],
            "summary": "Finfloo summary",
            "gaps": [],
            "language": "en",
            "custom_instructions": custom_instructions,
        },
        "chunks": chunks or [],
        "suggested_pills": ["A", "B", "C"],
        "language": "en",
        "created_at": 1000000,
    })


def _make_fresh_profile():
    """Simulates what generate_company_profile returns — no custom_instructions."""
    return CompanyProfile.model_validate({
        "name": "Finfloo",
        "industry": "Accounting",
        "services": ["Bookkeeping"],
        "out_of_scope": [],
        "summary": "Regenerated summary",
        "gaps": [],
        "language": "en",
        "custom_instructions": None,
    })


@pytest.mark.asyncio
async def test_enrich_preserves_custom_instructions():
    """custom_instructions must survive profile regeneration."""
    from app.routers.crawl import enrich_kb

    kb = _make_kb(custom_instructions="Always greet in Indonesian.")

    with patch("app.routers.crawl.generate_company_profile", AsyncMock(return_value=_make_fresh_profile())), \
         patch("app.routers.crawl.assess_quality_tier", return_value="rich"), \
         patch("app.routers.crawl.save_knowledge_base", AsyncMock(return_value=None)):
        result = await enrich_kb(kb, "kb_finfloo", {"Apa itu Finfloo?": "Finfloo adalah layanan akuntansi."})

    assert result.custom_instructions == "Always greet in Indonesian."


@pytest.mark.asyncio
async def test_enrich_preserves_null_custom_instructions():
    """None custom_instructions should stay None after enrichment."""
    from app.routers.crawl import enrich_kb

    kb = _make_kb(custom_instructions=None)

    with patch("app.routers.crawl.generate_company_profile", AsyncMock(return_value=_make_fresh_profile())), \
         patch("app.routers.crawl.assess_quality_tier", return_value="rich"), \
         patch("app.routers.crawl.save_knowledge_base", AsyncMock(return_value=None)):
        result = await enrich_kb(kb, "kb_finfloo", {"Q?": "A."})

    assert result.custom_instructions is None


@pytest.mark.asyncio
async def test_enrich_appends_chunk():
    """Each Q&A pair must be stored as a chunk with interview: prefix."""
    from app.routers.crawl import enrich_kb

    kb = _make_kb()

    with patch("app.routers.crawl.generate_company_profile", AsyncMock(return_value=_make_fresh_profile())), \
         patch("app.routers.crawl.assess_quality_tier", return_value="rich"), \
         patch("app.routers.crawl.save_knowledge_base", AsyncMock(return_value=None)):
        await enrich_kb(kb, "kb_finfloo", {"Berapa harganya?": "Mulai dari Rp1.500.000/bulan."})

    assert len(kb.chunks) == 1
    chunk = kb.chunks[0]
    assert chunk.source == "interview:Berapa harganya?"
    assert chunk.text == "Mulai dari Rp1.500.000/bulan."


@pytest.mark.asyncio
async def test_enrich_skips_blank_answers():
    """Answers that are whitespace-only must not create chunks."""
    from app.routers.crawl import enrich_kb

    kb = _make_kb()

    with patch("app.routers.crawl.generate_company_profile", AsyncMock(return_value=_make_fresh_profile())), \
         patch("app.routers.crawl.assess_quality_tier", return_value="rich"), \
         patch("app.routers.crawl.save_knowledge_base", AsyncMock(return_value=None)):
        await enrich_kb(kb, "kb_finfloo", {"Q?": "   ", "Real Q?": "Real answer."})

    sources = [c.source for c in kb.chunks]
    assert "interview:Q?" not in sources
    assert "interview:Real Q?" in sources


@pytest.mark.asyncio
async def test_enrich_no_profile_and_no_answers_raises():
    """With no prior profile and no valid answers, enrich must raise 400."""
    from fastapi import HTTPException
    from app.routers.crawl import enrich_kb

    kb = KnowledgeBase.model_validate({
        "job_id": "kb_new",
        "status": "complete",
        "progress": "",
        "pages_found": 0,
        "company_profile": None,
        "chunks": [],
        "suggested_pills": [],
        "language": "en",
        "created_at": 1000000,
    })

    with pytest.raises(HTTPException) as exc_info:
        await enrich_kb(kb, "kb_new", {"Q?": "   "})

    assert exc_info.value.status_code == 400
