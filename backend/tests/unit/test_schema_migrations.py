"""
Schema migration idempotency tests.

Verifies that init_db() runs cleanly on first call and can be safely
called again (all statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).

No credentials required — asyncpg pool is fully mocked.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


def _make_pool_mock():
    conn_mock = AsyncMock()
    pool_mock = MagicMock()
    pool_mock.acquire.return_value.__aenter__ = AsyncMock(return_value=conn_mock)
    pool_mock.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool_mock, conn_mock


class TestInitDbIdempotency:

    @pytest.mark.asyncio
    async def test_init_db_runs_without_error(self):
        """First run — all tables and indexes created, no exception raised."""
        pool_mock, _ = _make_pool_mock()
        with patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_get_pool, \
             patch("app.services.database.DATABASE_URL", "postgresql://fake"):
            mock_get_pool.return_value = pool_mock
            from app.services.database import init_db
            await init_db()

    @pytest.mark.asyncio
    async def test_init_db_idempotent_second_call(self):
        """Second run — IF NOT EXISTS / ADD COLUMN IF NOT EXISTS are no-ops, no error."""
        pool_mock, _ = _make_pool_mock()
        with patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_get_pool, \
             patch("app.services.database.DATABASE_URL", "postgresql://fake"):
            mock_get_pool.return_value = pool_mock
            from app.services.database import init_db
            await init_db()
            await init_db()

    @pytest.mark.asyncio
    async def test_init_db_skips_when_no_database_url(self):
        """No DATABASE_URL → returns immediately, pool is never touched."""
        with patch("app.services.database.DATABASE_URL", ""), \
             patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_get_pool:
            from app.services.database import init_db
            await init_db()
            mock_get_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_init_db_executes_expected_schema_statements(self):
        """init_db() executes all expected core schema and index statements."""
        pool_mock, conn_mock = _make_pool_mock()
        with patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_get_pool, \
             patch("app.services.database.DATABASE_URL", "postgresql://fake"):
            mock_get_pool.return_value = pool_mock
            from app.services.database import init_db
            await init_db()

            executed_sql = [
                call.args[0]
                for call in conn_mock.execute.call_args_list
                if call.args
            ]

            expected_fragments = [
                "CREATE TABLE IF NOT EXISTS knowledge_bases",
                "CREATE TABLE IF NOT EXISTS customer_configs",
                "ADD COLUMN IF NOT EXISTS webhook_url",
                "CREATE TABLE IF NOT EXISTS sessions",
                "CREATE TABLE IF NOT EXISTS users",
                "CREATE TABLE IF NOT EXISTS user_sites",
                "CREATE INDEX IF NOT EXISTS idx_user_sites_user_id",
                "CREATE INDEX IF NOT EXISTS idx_user_sites_kb_id",
                "CREATE TABLE IF NOT EXISTS briefs",
                "CREATE INDEX IF NOT EXISTS idx_briefs_kb_id",
                "ADD COLUMN IF NOT EXISTS greeting",
                "CREATE INDEX IF NOT EXISTS idx_sessions_kb_id",
                "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at",
            ]

            for fragment in expected_fragments:
                assert any(fragment in sql for sql in executed_sql), f"Missing statement: {fragment}"

    @pytest.mark.asyncio
    async def test_init_db_raises_on_pool_error(self):
        """Pool failure re-raises — lifespan handler in main.py catches and continues."""
        with patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_get_pool, \
             patch("app.services.database.DATABASE_URL", "postgresql://fake"):
            mock_get_pool.side_effect = Exception("asyncpg: connection refused")
            from app.services.database import init_db
            with pytest.raises(Exception, match="connection refused"):
                await init_db()
