"""
Third-party resilience tests.

These run in CI without any real credentials.  Each section tests one
external dependency: Upstash Redis, Neon (asyncpg), Firecrawl, and
OpenRouter (via the openai-compatible client).

The tests serve two purposes:
  1. Verify the app degrades gracefully when a service is down.
  2. Act as a canary — if an SDK changes its response shape or method
     names, these tests break before production does.
"""

import asyncio
import json
import os
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.models import CompanyProfile, PillSuggestions, Chunk
from app.services.llm import extract_json, _profile_from_partial


# ===========================================================================
# 1. Upstash Redis
# ===========================================================================

class TestRedisResilience:
    """app/services/redis.py — upstash_redis.asyncio.Redis"""

    @pytest.mark.asyncio
    async def test_get_knowledge_base_redis_down_returns_none(self):
        """Both Neon and Redis failing → None, never a 500."""
        with patch("app.services.database.db_get_knowledge_base", new_callable=AsyncMock) as mock_db, \
             patch("app.services.redis.redis.get", new_callable=AsyncMock) as mock_get:
            mock_db.side_effect = Exception("Neon connection refused")
            mock_get.side_effect = Exception("Upstash: unauthorized")
            from app.services.redis import get_knowledge_base
            result = await get_knowledge_base("job_abc")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_knowledge_base_neon_down_falls_back_to_redis(self):
        """Neon failure → silently falls back to Redis and returns KB."""
        import time as _time
        from app.models import KnowledgeBase
        kb = KnowledgeBase(
            job_id="job_abc", status="complete", created_at=int(_time.time()), chunks=[]
        )
        with patch("app.services.database.db_get_knowledge_base", new_callable=AsyncMock) as mock_db, \
             patch("app.services.redis.redis.get", new_callable=AsyncMock) as mock_get:
            mock_db.side_effect = Exception("Neon: SSL SYSCALL error")
            mock_get.return_value = kb.model_dump_json()
            from app.services.redis import get_knowledge_base
            result = await get_knowledge_base("job_abc")
            assert result is not None
            assert result.job_id == "job_abc"

    @pytest.mark.asyncio
    async def test_get_session_redis_down_propagates(self):
        """
        get_session has no error handling by design — callers (routers)
        will surface a 500.  This test documents that gap so we notice
        if someone silently swallows it.
        """
        with patch("app.services.redis.redis.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Upstash: connection timeout")
            from app.services.redis import get_session
            with pytest.raises(Exception, match="connection timeout"):
                await get_session("sess_abc")

    @pytest.mark.asyncio
    async def test_save_session_redis_down_propagates(self):
        """save_session has no error handling — exception bubbles up."""
        from app.models import Session
        session = Session(
            session_id="s1", kb_id="kb1", created_at=int(time.time())
        )
        with patch("app.services.redis.redis.set", new_callable=AsyncMock) as mock_set:
            mock_set.side_effect = Exception("Upstash: rate limit exceeded")
            from app.services.redis import save_session
            with pytest.raises(Exception, match="rate limit"):
                await save_session("s1", session)

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_down_propagates(self):
        """Rate-limit check has no error handling — Redis failure means 500."""
        with patch("app.services.redis.redis.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Upstash: token invalid")
            from app.services.redis import check_rate_limit
            with pytest.raises(Exception):
                await check_rate_limit("1.2.3.4", "crawl", 5, 60)


# ===========================================================================
# 2. Neon (asyncpg)
# ===========================================================================

class TestNeonResilience:
    """app/services/database.py — asyncpg + Neon"""

    @pytest.mark.asyncio
    async def test_get_customer_config_no_database_url_returns_none(self):
        """No DATABASE_URL env var → skip entirely, return None."""
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            # Reset the module-level DATABASE_URL cache
            with patch("app.services.database.DATABASE_URL", ""):
                from app.services.database import get_customer_config
                result = await get_customer_config("kb_abc")
                assert result is None

    @pytest.mark.asyncio
    async def test_get_customer_config_pool_failure_returns_none(self):
        """Pool creation failure → exception caught, returns None."""
        with patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_pool, \
             patch("app.services.database.DATABASE_URL", "postgresql://fake"):
            mock_pool.side_effect = Exception("asyncpg: connection refused")
            from app.services.database import get_customer_config
            result = await get_customer_config("kb_abc")
            assert result is None

    @pytest.mark.asyncio
    async def test_db_get_knowledge_base_no_database_url_returns_none(self):
        """No DATABASE_URL → db_get_knowledge_base returns None immediately."""
        with patch("app.services.database.DATABASE_URL", ""):
            from app.services.database import db_get_knowledge_base
            result = await db_get_knowledge_base("kb_abc")
            assert result is None

    @pytest.mark.asyncio
    async def test_db_get_knowledge_base_pool_failure_returns_none(self):
        """Pool error during kb fetch → caught, returns None."""
        with patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_pool, \
             patch("app.services.database.DATABASE_URL", "postgresql://fake"):
            mock_pool.side_effect = Exception("Neon: project paused (free tier)")
            from app.services.database import db_get_knowledge_base
            result = await db_get_knowledge_base("kb_abc")
            assert result is None

    @pytest.mark.asyncio
    async def test_neon_schema_change_returns_none(self):
        """If the Neon schema changes (e.g. column removed), fetchrow fails → None."""
        conn_mock = AsyncMock()
        conn_mock.fetchrow.side_effect = Exception("column 'data' does not exist")
        pool_mock = MagicMock()
        pool_mock.acquire.return_value.__aenter__ = AsyncMock(return_value=conn_mock)
        pool_mock.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_pool, \
             patch("app.services.database.DATABASE_URL", "postgresql://fake"):
            mock_pool.return_value = pool_mock
            from app.services.database import db_get_knowledge_base
            result = await db_get_knowledge_base("kb_abc")
            assert result is None


# ===========================================================================
# 3. Firecrawl
# ===========================================================================

class TestFirecrawlResilience:
    """app/services/crawler.py — firecrawl SDK"""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty_result(self):
        """FIRECRAWL_API_KEY absent → empty CrawlResult, no crash."""
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": ""}):
            from app.services.crawler import _crawl_site_firecrawl
            result = await _crawl_site_firecrawl("https://example.com")
            assert result.pages == []
            assert result.total_pages == 0

    @pytest.mark.asyncio
    async def test_firecrawl_sdk_raises_propagates(self):
        """
        If Firecrawl's crawl() raises (credits exhausted, SDK incompatibility),
        the exception is NOT caught — it propagates to the router.
        This test documents that gap.
        """
        mock_fc_instance = MagicMock()
        mock_fc_instance.crawl.side_effect = Exception("402 Payment Required")

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-fake"}), \
             patch("app.services.crawler.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = Exception("402 Payment Required")
            from app.services.crawler import _crawl_site_firecrawl
            with pytest.raises(Exception, match="402"):
                await _crawl_site_firecrawl("https://example.com")

    @pytest.mark.asyncio
    async def test_firecrawl_result_no_data_attr_returns_empty(self):
        """SDK returns object without .data (API shape change) → empty pages, no crash."""
        mock_result = MagicMock(spec=[])  # no attributes at all

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-fake"}), \
             patch("app.services.crawler.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = mock_result
            from app.services.crawler import _crawl_site_firecrawl
            result = await _crawl_site_firecrawl("https://example.com")
            assert result.pages == []

    @pytest.mark.asyncio
    async def test_firecrawl_page_with_no_markdown_is_skipped(self):
        """Pages with empty markdown content are filtered out."""
        doc = MagicMock()
        doc.markdown = ""
        mock_result = MagicMock()
        mock_result.data = [doc]

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-fake"}), \
             patch("app.services.crawler.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = mock_result
            from app.services.crawler import _crawl_site_firecrawl
            result = await _crawl_site_firecrawl("https://example.com")
            assert result.pages == []

    @pytest.mark.asyncio
    async def test_firecrawl_page_missing_metadata_uses_url_fallback(self):
        """Page with no metadata → URL used as both source and title, no crash."""
        doc = MagicMock()
        doc.markdown = "Some content here"
        doc.metadata = {}  # empty dict, no sourceURL or title keys

        mock_result = MagicMock()
        mock_result.data = [doc]

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-fake"}), \
             patch("app.services.crawler.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = mock_result
            from app.services.crawler import _crawl_site_firecrawl
            result = await _crawl_site_firecrawl("https://example.com")
            assert len(result.pages) == 1
            assert result.pages[0].text == "Some content here"


# ===========================================================================
# 4. OpenRouter (via openai-compatible client)
# ===========================================================================

class TestOpenRouterResilience:
    """app/services/llm.py — openai.AsyncOpenAI pointing at openrouter.ai"""

    # ── extract_json (sync, pure) ────────────────────────────────────────────

    def test_extract_json_valid(self):
        assert extract_json('{"key": "value"}') == {"key": "value"}

    def test_extract_json_json_wrapped_in_prose(self):
        """LLM adds preamble → we still extract the JSON."""
        text = 'Sure! Here is the result:\n{"name": "Acme"}\nHope that helps.'
        result = extract_json(text)
        assert result == {"name": "Acme"}

    def test_extract_json_invalid_raises(self):
        """Completely non-JSON response → raises, callers must handle."""
        with pytest.raises((json.JSONDecodeError, ValueError)):
            extract_json("Sorry, I cannot help with that.")

    def test_extract_json_empty_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            extract_json("")

    # ── _profile_from_partial ───────────────────────────────────────────────

    def test_profile_from_partial_empty_dict_returns_valid_profile(self):
        """If the model returns {}, we still get a valid CompanyProfile."""
        profile = _profile_from_partial({}, "https://example.com")
        assert isinstance(profile, CompanyProfile)
        assert profile.name == "https://example.com"  # falls back to site_url
        assert profile.industry == "Business"
        assert profile.services == []
        assert profile.gaps == []

    def test_profile_from_partial_services_as_comma_string(self):
        """OpenRouter sometimes returns services as a comma-separated string."""
        profile = _profile_from_partial(
            {"services": "Consulting, Design, Development"}, "https://x.com"
        )
        assert profile.services == ["Consulting", "Design", "Development"]

    def test_profile_from_partial_contact_as_email_string(self):
        """Contact returned as a plain email string → wrapped in dict."""
        profile = _profile_from_partial(
            {"contact": "hello@acme.com"}, "https://acme.com"
        )
        assert profile.contact == {"email": "hello@acme.com"}

    def test_profile_from_partial_contact_as_phone_string(self):
        """Contact returned as phone string → wrapped with phone key."""
        profile = _profile_from_partial(
            {"contact": "+1-800-CALL-ME"}, "https://acme.com"
        )
        assert profile.contact == {"phone": "+1-800-CALL-ME"}

    def test_profile_from_partial_gaps_as_string_wrapped(self):
        """Gaps returned as a plain string → wrapped in a list."""
        profile = _profile_from_partial(
            {"gaps": "No pricing page"}, "https://acme.com"
        )
        assert profile.gaps == ["No pricing page"]

    # ── generate_company_profile: API failure ───────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_company_profile_network_error_propagates(self):
        """
        GAP: generate_company_profile only catches (ValidationError, JSONDecodeError,
        KeyError, TypeError).  A generic network exception propagates unhandled →
        the router will return a 500.  This test documents that known gap.
        """
        fake_chunks = [
            Chunk(id="c1", source="homepage", text="We are Acme Corp.", word_count=5)
        ]
        with patch("app.services.llm._call_profile_model", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("openai.APIConnectionError: connection refused")
            from app.services.llm import generate_company_profile
            with pytest.raises(Exception, match="connection refused"):
                await generate_company_profile(fake_chunks, "https://acme.com")

    @pytest.mark.asyncio
    async def test_generate_company_profile_json_decode_error_uses_partial(self):
        """
        When _call_profile_model raises JSONDecodeError (e.g. model returns prose),
        generate_company_profile catches it on the second attempt and falls back to
        _profile_from_partial, returning a degraded but valid profile.

        Note: we patch _call_profile_model directly (not the underlying LLM client)
        so that tenacity's RetryError wrapper is bypassed — the catch list in
        generate_company_profile targets the unwrapped exception types.
        """
        fake_chunks = [
            Chunk(id="c1", source="homepage", text="We are Acme Corp.", word_count=5)
        ]
        with patch("app.services.llm._call_profile_model", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = json.JSONDecodeError("Expecting value", "", 0)
            from app.services.llm import generate_company_profile
            profile = await generate_company_profile(fake_chunks, "https://acme.com")
            assert isinstance(profile, CompanyProfile)


# ===========================================================================
# 5. crawl_site: httpx → Firecrawl fallback
# ===========================================================================

class TestCrawlSiteFallback:
    """app/services/crawler.py — crawl_site() fallback logic"""

    @pytest.mark.asyncio
    async def test_thin_httpx_result_triggers_firecrawl(self):
        """<100 words from httpx → Firecrawl is called as fallback."""
        from app.services.crawler import CrawlResult, PageContent

        thin_result = CrawlResult(
            pages=[PageContent(url="https://x.com", title="X", text="Short text")],
            total_pages=1,
            duration_ms=100,
        )
        rich_result = CrawlResult(
            pages=[PageContent(url="https://x.com", title="X", text=" ".join(["word"] * 150))],
            total_pages=1,
            duration_ms=200,
        )

        with patch("app.services.crawler._crawl_site_httpx", new_callable=AsyncMock) as mock_httpx, \
             patch("app.services.crawler._crawl_site_firecrawl", new_callable=AsyncMock) as mock_fc:
            mock_httpx.return_value = thin_result
            mock_fc.return_value = rich_result
            from app.services.crawler import crawl_site
            result = await crawl_site("https://x.com")
            mock_fc.assert_called_once()
            assert result == rich_result

    @pytest.mark.asyncio
    async def test_rich_httpx_result_skips_firecrawl(self):
        """>=100 words from httpx → Firecrawl is never called."""
        from app.services.crawler import CrawlResult, PageContent

        rich_result = CrawlResult(
            pages=[PageContent(url="https://x.com", title="X", text=" ".join(["word"] * 150))],
            total_pages=1,
            duration_ms=100,
        )

        with patch("app.services.crawler._crawl_site_httpx", new_callable=AsyncMock) as mock_httpx, \
             patch("app.services.crawler._crawl_site_firecrawl", new_callable=AsyncMock) as mock_fc:
            mock_httpx.return_value = rich_result
            from app.services.crawler import crawl_site
            result = await crawl_site("https://x.com")
            mock_fc.assert_not_called()
            assert result == rich_result
