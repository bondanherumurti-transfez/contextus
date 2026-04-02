from upstash_redis import Redis
import os
from dotenv import load_dotenv
from app.models import KnowledgeBase, Session

load_dotenv()

redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL", ""),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN", ""),
)


def kb_key(job_id: str) -> str:
    return f"kb:{job_id}"


def session_key(session_id: str) -> str:
    return f"session:{session_id}"


def rate_key(ip: str, action: str) -> str:
    return f"rate:{ip}:{action}"


async def save_knowledge_base(
    job_id: str, data: KnowledgeBase, ttl: int | None = 1800
) -> None:
    redis.set(kb_key(job_id), data.model_dump_json(), ex=ttl)


async def get_knowledge_base(job_id: str) -> KnowledgeBase | None:
    raw = redis.get(kb_key(job_id))
    if raw is None:
        return None
    return KnowledgeBase.model_validate_json(raw)


async def save_session(session_id: str, data: Session, ttl: int = 1800) -> None:
    redis.set(session_key(session_id), data.model_dump_json(), ex=ttl)


async def get_session(session_id: str) -> Session | None:
    raw = redis.get(session_key(session_id))
    if raw is None:
        return None
    return Session.model_validate_json(raw)


async def check_rate_limit(
    ip: str, action: str, max_requests: int, window_secs: int
) -> bool:
    key = rate_key(ip, action)
    current = redis.get(key)
    if current is None:
        redis.set(key, "1", ex=window_secs)
        return True
    count = int(current)
    if count >= max_requests:
        return False
    redis.incr(key)
    return True


async def get_rate_limit_count(ip: str, action: str) -> int:
    key = rate_key(ip, action)
    current = redis.get(key)
    if current is None:
        return 0
    return int(current)


async def extend_session_ttl(session_id: str, ttl: int = 86400) -> None:
    """Extend session TTL — called when contact is captured to survive until cron runs."""
    redis.expire(session_key(session_id), ttl)


async def scan_all_sessions() -> list[Session]:
    """Scan all session:* keys and return deserialized Session objects."""
    sessions = []
    cursor = 0
    while True:
        cursor, keys = redis.scan(cursor, match="session:*", count=100)
        for key in keys:
            raw = redis.get(key)
            if raw:
                try:
                    sessions.append(Session.model_validate_json(raw))
                except Exception:
                    pass
        if cursor == 0:
            break
    return sessions
