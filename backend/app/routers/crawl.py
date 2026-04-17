from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Header
from pydantic import BaseModel
from nanoid import generate
import time

from app.models import (
    KnowledgeBase,
    CompanyProfile,
    CrawlRequest,
    CrawlResponse,
    EnrichRequest,
    UpdatePillsRequest,
    Chunk,
)
from app.services.redis import save_knowledge_base, get_knowledge_base, check_rate_limit
from app.services.database import save_customer_config, db_get_knowledge_base
from app.services.crawler import crawl_site, validate_url
from app.services.chunker import chunk_pages
from app.services.llm import generate_company_profile, assess_quality_tier, select_pills
from app.services.turnstile import verify_turnstile

router = APIRouter(tags=["crawl"])


DEMO_URL = "https://getcontextus.dev"
DEMO_JOB_ID = "demo"


async def run_crawl_job(
    job_id: str, url: str, ttl: int | None = 1800, permanent: bool = False, lang_hint: str | None = None
):
    try:
        kb = await get_knowledge_base(job_id)
        if not kb:
            return

        kb.status = "analyzing"
        kb.progress = "Analyzing website content..."
        await save_knowledge_base(job_id, kb, ttl=ttl, permanent=permanent)

        def on_progress(msg: str):
            kb.progress = msg

        result = await crawl_site(url, on_progress)

        kb.pages_found = result.total_pages
        kb.progress = "Extracting content..."
        await save_knowledge_base(job_id, kb, ttl=ttl, permanent=permanent)

        chunks = chunk_pages(result.pages)

        if chunks:
            kb.progress = "Generating company profile..."
            await save_knowledge_base(job_id, kb, ttl=ttl, permanent=permanent)

            company_profile = await generate_company_profile(chunks, url, lang_hint=lang_hint)
            kb.company_profile = company_profile
            kb.chunks = chunks
            kb.quality_tier = assess_quality_tier(chunks)
            kb.language = company_profile.language
            kb.suggested_pills = select_pills(company_profile.pill_suggestions, language=company_profile.language)

        kb.status = "complete"
        kb.progress = ""
        await save_knowledge_base(job_id, kb, ttl=ttl, permanent=permanent)

    except Exception as e:
        kb = await get_knowledge_base(job_id)
        if kb:
            kb.status = "failed"
            kb.progress = str(e)
            await save_knowledge_base(job_id, kb, ttl=ttl)


@router.post("/crawl/demo")
async def seed_demo_kb(background_tasks: BackgroundTasks, force: bool = False):
    """Seed or refresh the permanent demo knowledge base (stored in Neon)."""
    existing = await get_knowledge_base(DEMO_JOB_ID)
    if existing and existing.status == "complete" and not force:
        return {"job_id": DEMO_JOB_ID, "status": "complete", "cached": True}

    kb = KnowledgeBase(
        job_id=DEMO_JOB_ID,
        status="crawling",
        progress="Starting demo crawl...",
        created_at=int(time.time()),
    )
    await save_knowledge_base(DEMO_JOB_ID, kb, ttl=None, permanent=True)
    background_tasks.add_task(run_crawl_job, DEMO_JOB_ID, DEMO_URL, None, True)
    return {"job_id": DEMO_JOB_ID, "status": "crawling"}


class SeedRequest(BaseModel):
    url: str
    kb_id: str
    notion_db_id: str | None = None
    allowed_origins: list[str] = []
    lang: str | None = None  # force pill language, e.g. "id"; auto-detected if omitted


@router.post("/crawl/seed")
async def seed_customer_kb(
    body: SeedRequest,
    background_tasks: BackgroundTasks,
    x_admin_secret: str | None = Header(default=None),
):
    """Seed a permanent customer KB (stored in Neon). Admin-protected."""
    import os
    from nanoid import generate as nanoid_generate

    admin_secret = os.getenv("ADMIN_SECRET", "")
    if admin_secret and x_admin_secret != admin_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not validate_url(body.url):
        raise HTTPException(status_code=400, detail="Invalid URL")

    token = f"pk_{body.kb_id}_{nanoid_generate(size=8)}"

    config = {
        "kb_id": body.kb_id,
        "url": body.url,
        "notion_db_id": body.notion_db_id,
        "allowed_origins": body.allowed_origins,
        "token": token,
        "created_at": int(time.time()),
    }
    await save_customer_config(config)

    kb = KnowledgeBase(
        job_id=body.kb_id,
        status="crawling",
        progress="Starting crawl...",
        created_at=int(time.time()),
    )
    await save_knowledge_base(body.kb_id, kb, ttl=None, permanent=True)
    background_tasks.add_task(run_crawl_job, body.kb_id, body.url, None, True, body.lang)

    return {"kb_id": body.kb_id, "status": "crawling", "token": token}


@router.post("/crawl", response_model=CrawlResponse)
async def start_crawl(
    request: Request, body: CrawlRequest, background_tasks: BackgroundTasks
):
    client_ip = request.client.host if request.client else "unknown"

    if not await verify_turnstile(body.cf_turnstile_response or "", client_ip):
        raise HTTPException(status_code=403, detail="Turnstile verification failed")

    if not validate_url(body.url):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Must be http/https and not a private IP.",
        )

    if not await check_rate_limit(client_ip, "crawl", 30, 3600):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Max 30 crawls per hour."
        )

    job_id = generate(size=10)

    kb = KnowledgeBase(
        job_id=job_id,
        status="crawling",
        progress="Starting crawl...",
        created_at=int(time.time()),
    )
    await save_knowledge_base(job_id, kb)

    background_tasks.add_task(run_crawl_job, job_id, body.url)

    return CrawlResponse(job_id=job_id, status="crawling")


@router.get("/crawl/{job_id}")
async def get_crawl_status(job_id: str):
    kb = await get_knowledge_base(job_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Job not found")
    return kb


@router.post("/crawl/{job_id}/enrich", response_model=CompanyProfile)
async def enrich_knowledge_base(job_id: str, body: EnrichRequest):
    kb = await get_knowledge_base(job_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Job not found")

    if kb.status != "complete":
        raise HTTPException(status_code=400, detail="Job not complete yet")

    from nanoid import generate as gen_id

    for question, answer in body.answers.items():
        if answer.strip():
            chunk = Chunk(
                id=gen_id(size=10),
                source=f"interview:{question}",
                text=answer,
                word_count=len(answer.split()),
            )
            kb.chunks.append(chunk)

    if kb.chunks:
        new_profile = await generate_company_profile(kb.chunks, f"enriched:{job_id}")
        kb.company_profile = new_profile
        kb.quality_tier = assess_quality_tier(kb.chunks)

    await save_knowledge_base(job_id, kb)

    return kb.company_profile


@router.patch("/crawl/{job_id}/pills")
async def update_pills(
    job_id: str,
    body: UpdatePillsRequest,
    x_admin_secret: str | None = Header(default=None),
):
    kb = await get_knowledge_base(job_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Job not found")

    if kb.status != "complete":
        raise HTTPException(status_code=400, detail="Job not complete yet")

    if len(body.pills) != 3:
        raise HTTPException(status_code=400, detail="Exactly 3 pills required")

    # Permanent KBs (found in Neon) require admin auth. Fail closed on DB errors
    # so a Neon outage cannot be used to bypass auth.
    import os as _os
    permanent = False
    if _os.getenv("DATABASE_URL", ""):
        try:
            permanent = await db_get_knowledge_base(job_id) is not None
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Unable to verify knowledge base persistence; please retry later",
            )

    if permanent:
        import os
        admin_secret = os.getenv("ADMIN_SECRET", "")
        if not admin_secret:
            raise HTTPException(status_code=500, detail="Server misconfiguration: ADMIN_SECRET not set")
        if x_admin_secret != admin_secret:
            raise HTTPException(status_code=401, detail="Unauthorized")

    kb.suggested_pills = body.pills
    if permanent:
        await save_knowledge_base(job_id, kb, permanent=True, ttl=None)
    else:
        await save_knowledge_base(job_id, kb)

    return {"job_id": job_id, "suggested_pills": kb.suggested_pills}
