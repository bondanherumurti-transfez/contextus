from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from nanoid import generate
import time

from app.models import (
    KnowledgeBase,
    CompanyProfile,
    CrawlRequest,
    CrawlResponse,
    EnrichRequest,
)
from app.services.redis import save_knowledge_base, get_knowledge_base, check_rate_limit
from app.services.crawler import crawl_site, validate_url
from app.services.chunker import chunk_pages
from app.services.llm import generate_company_profile, assess_quality_tier

router = APIRouter(tags=["crawl"])


async def run_crawl_job(job_id: str, url: str):
    try:
        kb = await get_knowledge_base(job_id)
        if not kb:
            return

        kb.status = "analyzing"
        kb.progress = "Analyzing website content..."
        await save_knowledge_base(job_id, kb)

        def on_progress(msg: str):
            kb.progress = msg

        result = await crawl_site(url, on_progress)

        kb.pages_found = result.total_pages
        kb.progress = "Extracting content..."
        await save_knowledge_base(job_id, kb)

        chunks = chunk_pages(result.pages)

        if chunks:
            kb.progress = "Generating company profile..."
            await save_knowledge_base(job_id, kb)

            company_profile = generate_company_profile(chunks, url)
            kb.company_profile = company_profile
            kb.chunks = chunks
            kb.quality_tier = assess_quality_tier(chunks)

        kb.status = "complete"
        kb.progress = ""
        await save_knowledge_base(job_id, kb)

    except Exception as e:
        kb = await get_knowledge_base(job_id)
        if kb:
            kb.status = "failed"
            kb.progress = str(e)
            await save_knowledge_base(job_id, kb)


@router.post("/crawl", response_model=CrawlResponse)
async def start_crawl(
    request: Request, body: CrawlRequest, background_tasks: BackgroundTasks
):
    client_ip = request.client.host if request.client else "unknown"

    # Validate URL first — don't count invalid/malicious requests against the rate limit
    if not validate_url(body.url):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Must be http/https and not a private IP.",
        )

    if not await check_rate_limit(client_ip, "crawl", 3, 3600):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Max 3 crawls per hour."
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

    from app.services.chunker import chunk_text
    from nanoid import generate as gen_id

    for question, answer in body.answers.items():
        if answer.strip():
            chunk = type(
                "Chunk",
                (),
                {
                    "id": gen_id(size=10),
                    "source": f"interview:{question}",
                    "text": answer,
                    "word_count": len(answer.split()),
                },
            )()
            kb.chunks.append(chunk)

    if kb.chunks:
        new_profile = generate_company_profile(kb.chunks, f"enriched:{job_id}")
        kb.company_profile = new_profile
        kb.quality_tier = assess_quality_tier(kb.chunks)

    await save_knowledge_base(job_id, kb)

    return kb.company_profile
