import os
import time
import json
import logging
import asyncpg
from dotenv import load_dotenv

from app.models import KnowledgeBase, Session

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=10,
            timeout=10,
        )
    return _pool


async def init_db():
    """Create tables if they don't exist. Called on app startup."""
    if not DATABASE_URL:
        logger.warning("[db] DATABASE_URL not set — skipping Neon init")
        return
    logger.info("[db] Connecting to Neon...")
    try:
        pool = await get_pool()
        logger.info("[db] Pool created OK")
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_bases (
                    kb_id       TEXT PRIMARY KEY,
                    url         TEXT,
                    data        JSONB NOT NULL,
                    created_at  BIGINT NOT NULL,
                    updated_at  BIGINT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customer_configs (
                    kb_id           TEXT PRIMARY KEY,
                    url             TEXT,
                    notion_db_id    TEXT,
                    allowed_origins TEXT[],
                    token           TEXT,
                    webhook_url     TEXT,
                    created_at      BIGINT NOT NULL
                )
            """)
            await conn.execute("""
                ALTER TABLE customer_configs
                ADD COLUMN IF NOT EXISTS webhook_url TEXT
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id       TEXT PRIMARY KEY,
                    kb_id            TEXT         NOT NULL,
                    messages         JSONB        NOT NULL DEFAULT '[]',
                    message_count    INTEGER      NOT NULL DEFAULT 0,
                    contact_captured BOOLEAN      NOT NULL DEFAULT FALSE,
                    contact_value    TEXT,
                    brief_sent       BOOLEAN      NOT NULL DEFAULT FALSE,
                    created_at       BIGINT       NOT NULL,
                    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            """)
        logger.info("[db] Neon DB tables ready")
    except Exception as e:
        logger.error("[db] Neon init failed: %s", e)
        raise


# ── Knowledge bases ──────────────────────────────────────────────────────────

async def db_save_knowledge_base(kb: KnowledgeBase) -> None:
    if not DATABASE_URL:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO knowledge_bases (kb_id, url, data, created_at, updated_at)
            VALUES ($1, $2, $3::jsonb, $4, $5)
            ON CONFLICT (kb_id) DO UPDATE
                SET data = EXCLUDED.data,
                    updated_at = EXCLUDED.updated_at
        """, kb.kb_id if hasattr(kb, 'kb_id') else kb.job_id,
            None,
            kb.model_dump_json(),
            kb.created_at,
            int(time.time()))


async def db_get_knowledge_base(kb_id: str) -> KnowledgeBase | None:
    if not DATABASE_URL:
        return None
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM knowledge_bases WHERE kb_id = $1", kb_id
            )
        if row:
            return KnowledgeBase.model_validate_json(row["data"])
    except Exception as e:
        logger.error("db_get_knowledge_base error: %s", e)
    return None


# ── Customer configs ─────────────────────────────────────────────────────────

async def save_customer_config(config: dict) -> None:
    if not DATABASE_URL:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO customer_configs
                (kb_id, url, notion_db_id, allowed_origins, token, webhook_url, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (kb_id) DO UPDATE
                SET url            = EXCLUDED.url,
                    notion_db_id   = EXCLUDED.notion_db_id,
                    allowed_origins= EXCLUDED.allowed_origins,
                    token          = EXCLUDED.token,
                    webhook_url    = EXCLUDED.webhook_url
        """,
            config.get("kb_id"),
            config.get("url"),
            config.get("notion_db_id"),
            config.get("allowed_origins") or [],
            config.get("token"),
            config.get("webhook_url"),
            config.get("created_at", int(time.time())),
        )


async def get_customer_config(kb_id: str) -> dict | None:
    if not DATABASE_URL:
        return None
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM customer_configs WHERE kb_id = $1", kb_id
            )
        if row:
            return dict(row)
    except Exception as e:
        logger.error("get_customer_config error: %s", e)
    return None


# ── Sessions ─────────────────────────────────────────────────────────────────

async def archive_session(data: Session) -> None:
    if not DATABASE_URL:
        return
    try:
        pool = await get_pool()
        messages_json = json.dumps([m.model_dump() for m in data.messages])
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO sessions (
                    session_id, kb_id, messages, message_count,
                    contact_captured, contact_value, brief_sent, created_at, updated_at
                ) VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, now())
                ON CONFLICT (session_id) DO UPDATE SET
                    messages         = EXCLUDED.messages,
                    message_count    = EXCLUDED.message_count,
                    contact_captured = EXCLUDED.contact_captured,
                    contact_value    = EXCLUDED.contact_value,
                    brief_sent       = EXCLUDED.brief_sent,
                    updated_at       = now()
            """,
                data.session_id, data.kb_id, messages_json, len(data.messages),
                data.contact_captured, data.contact_value, data.brief_sent,
                data.created_at,
            )
    except Exception as e:
        logger.error("[db] archive_session error: %s", e)


async def db_mark_brief_sent(session_id: str) -> None:
    if not DATABASE_URL:
        return
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET brief_sent = true, updated_at = now() WHERE session_id = $1",
                session_id,
            )
    except Exception as e:
        logger.error("[db] db_mark_brief_sent error: %s", e)
