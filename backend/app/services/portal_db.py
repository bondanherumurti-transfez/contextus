import time
import logging
import asyncpg
from nanoid import generate as nanoid_generate

from app.services.database import get_pool, DATABASE_URL

logger = logging.getLogger(__name__)

UserRow = dict


async def db_get_user_by_id(user_id: str) -> UserRow | None:
    if not DATABASE_URL:
        return None
    # Intentionally re-raises on DB error so get_current_user() can return 503
    # instead of collapsing infra failures into "user not found" (401).
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    return dict(row) if row else None


async def db_get_user_by_google_sub(google_sub: str) -> UserRow | None:
    if not DATABASE_URL:
        return None
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE google_sub = $1", google_sub)
        return dict(row) if row else None
    except Exception as e:
        logger.error("db_get_user_by_google_sub error: %s", e)
        return None


async def db_get_user_by_email_no_sub(email: str) -> UserRow | None:
    """Find a pre-seeded user (google_sub IS NULL) by email — seed-then-login path."""
    if not DATABASE_URL:
        return None
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1 AND google_sub IS NULL", email
            )
        return dict(row) if row else None
    except Exception as e:
        logger.error("db_get_user_by_email_no_sub error: %s", e)
        return None


async def db_create_user(email: str, google_sub: str, display_name: str | None) -> UserRow:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set — cannot create user")
    user_id = f"usr_{nanoid_generate(size=12)}"
    now = int(time.time())
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (user_id, email, google_sub, display_name, created_at, last_login_at)
                VALUES ($1, $2, $3, $4, $5, $5)
                RETURNING *
                """,
                user_id, email, google_sub, display_name, now,
            )
        return dict(row)
    except Exception as e:
        logger.error("db_create_user error: %s", e)
        raise


async def db_update_user_login(user_id: str, display_name: str | None, last_login_at: int) -> None:
    if not DATABASE_URL:
        return
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET last_login_at = $1, display_name = COALESCE($2, display_name)
                WHERE user_id = $3
                """,
                last_login_at, display_name, user_id,
            )
    except Exception as e:
        logger.error("db_update_user_login error: %s", e)


async def db_set_google_sub(user_id: str, google_sub: str) -> bool:
    """Atomically claim google_sub only when the row still has google_sub IS NULL.

    Returns True if the row was updated, False if it was already claimed
    (concurrent login). Caller should handle False gracefully.
    """
    if not DATABASE_URL:
        return False
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE users
                SET google_sub = $1
                WHERE user_id = $2 AND google_sub IS NULL
                RETURNING user_id
                """,
                google_sub, user_id,
            )
        return row is not None
    except Exception as e:
        logger.error("db_set_google_sub error: %s", e)
        return False


async def db_user_has_kb_access(user_id: str, kb_id: str) -> bool:
    if not DATABASE_URL:
        return False
    # Intentionally re-raises on DB error so get_current_user_for_kb() can
    # return 503 instead of silently treating infra failures as 403 forbidden.
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM user_sites WHERE user_id = $1 AND kb_id = $2",
            user_id, kb_id,
        )
    return row is not None


async def db_get_user_sites(user_id: str) -> list[dict]:
    if not DATABASE_URL:
        return []
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    us.kb_id,
                    cc.url,
                    kb.data::jsonb->'company_profile'->>'name' AS name,
                    us.kb_id                                    AS token,
                    us.created_at,
                    kb.updated_at                               AS last_crawled_at,
                    (kb.data::jsonb->>'pages_found')::int       AS pages_indexed
                FROM user_sites us
                LEFT JOIN customer_configs cc ON cc.kb_id = us.kb_id
                LEFT JOIN knowledge_bases  kb ON kb.kb_id = us.kb_id
                WHERE us.user_id = $1
                ORDER BY us.created_at DESC
                """,
                user_id,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("db_get_user_sites error: %s", e)
        return []


async def db_claim_site(email: str, kb_id: str) -> bool:
    """Link a user (by email) to a kb_id. Creates user row if email not found.

    Raises ValueError if kb_id doesn't exist in customer_configs (FK violation).
    """
    pool = await get_pool()
    now = int(time.time())
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT user_id FROM users WHERE email = $1", email)
            if row:
                user_id = row["user_id"]
            else:
                candidate_id = f"usr_{nanoid_generate(size=12)}"
                await conn.execute(
                    """
                    INSERT INTO users (user_id, email, google_sub, display_name, created_at, last_login_at)
                    VALUES ($1, $2, NULL, NULL, $3, $3)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    candidate_id, email, now,
                )
                refetch = await conn.fetchrow("SELECT user_id FROM users WHERE email = $1", email)
                user_id = refetch["user_id"]

            await conn.execute(
                """
                INSERT INTO user_sites (user_id, kb_id, created_at)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
                """,
                user_id, kb_id, now,
            )
    except asyncpg.ForeignKeyViolationError:
        raise ValueError(f"kb_id '{kb_id}' does not exist in customer_configs")
    return True


async def db_revoke_site(email: str, kb_id: str) -> bool:
    """Remove a user↔kb_id link by email. Returns True if a row was deleted."""
    if not DATABASE_URL:
        return False
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id FROM users WHERE email = $1", email)
        if not row:
            return False
        result = await conn.execute(
            "DELETE FROM user_sites WHERE user_id = $1 AND kb_id = $2",
            row["user_id"], kb_id,
        )
    return result == "DELETE 1"
