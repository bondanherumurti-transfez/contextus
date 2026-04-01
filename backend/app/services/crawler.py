import os
import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Callable
from dataclasses import dataclass
import time


@dataclass
class PageContent:
    url: str
    title: str
    text: str


@dataclass
class CrawlResult:
    pages: list[PageContent]
    total_pages: int
    duration_ms: int


BLOCKED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".mp4",
    ".mp3",
    ".zip",
    ".exe",
}
BOILERPLATE_TAGS = ["nav", "footer", "header", "script", "style", "aside", "form"]

PRIORITY_KEYWORDS = ["about", "service", "product", "pricing", "contact", "team", "feature", "solution", "why", "how"]
DEPRIORITY_KEYWORDS = ["blog", "news", "post", "article", "tag", "category", "author"]
MAX_PAGES = 10


def score_url(url: str) -> int:
    path = urlparse(url).path.lower()
    if any(kw in path for kw in PRIORITY_KEYWORDS):
        return 2
    if any(kw in path for kw in DEPRIORITY_KEYWORDS):
        return 0
    return 1

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def is_valid_url(url: str, base_domain: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if parsed.netloc != base_domain:
            return False
        path_lower = parsed.path.lower()
        for ext in BLOCKED_EXTENSIONS:
            if path_lower.endswith(ext):
                return False
        if any(x in path_lower for x in ["#", "mailto:", "tel:", "javascript:"]):
            return False
        return True
    except Exception:
        return False


async def fetch_page(
    client: httpx.AsyncClient, url: str
) -> tuple[str, str, str] | None:
    try:
        response = await client.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else url

        body = soup.find("body")
        if body:
            for tag in BOILERPLATE_TAGS:
                for element in body.find_all(tag):
                    element.decompose()
            text = body.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

        text = " ".join(text.split())
        return (url, title, text)
    except Exception:
        return None


async def _crawl_site_httpx(
    url: str, on_progress: Callable[[str], None] | None = None
) -> CrawlResult:
    start_time = time.time()

    parsed = urlparse(url)
    base_domain = parsed.netloc

    async with httpx.AsyncClient(headers=HEADERS) as client:
        if on_progress:
            on_progress(f"Fetching {url}...")

        homepage_result = await fetch_page(client, url)
        if not homepage_result:
            return CrawlResult(
                pages=[],
                total_pages=0,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        pages = [
            PageContent(
                url=homepage_result[0],
                title=homepage_result[1],
                text=homepage_result[2],
            )
        ]

        soup = BeautifulSoup((await client.get(url)).text, "html.parser")
        links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(url, href)
            normalized = full_url.split("#")[0].rstrip("/")
            if is_valid_url(normalized, base_domain) and normalized != url.rstrip("/"):
                links.add(normalized)

        links = sorted(links, key=score_url, reverse=True)[:MAX_PAGES - 1]

        if on_progress:
            on_progress(f"Found {len(links) + 1} pages to crawl...")

        semaphore = asyncio.Semaphore(5)

        async def fetch_with_semaphore(link: str) -> tuple[str, str, str] | None:
            async with semaphore:
                return await fetch_page(client, link)

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[fetch_with_semaphore(link) for link in links]),
                timeout=30.0,
            )

            for result in results:
                if result:
                    pages.append(
                        PageContent(url=result[0], title=result[1], text=result[2])
                    )
        except asyncio.TimeoutError:
            if on_progress:
                on_progress("Crawl timed out, returning partial results...")

    duration_ms = int((time.time() - start_time) * 1000)

    if on_progress:
        on_progress(f"Crawled {len(pages)} pages in {duration_ms}ms")

    return CrawlResult(pages=pages, total_pages=len(pages), duration_ms=duration_ms)


async def _crawl_site_firecrawl(
    url: str, on_progress: Callable[[str], None] | None = None
) -> CrawlResult:
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return CrawlResult(pages=[], total_pages=0, duration_ms=0)

    from firecrawl import Firecrawl

    start_time = time.time()
    app = Firecrawl(api_key=api_key)

    if on_progress:
        on_progress("Trying alternative crawler...")

    result = await asyncio.to_thread(
        lambda: app.crawl(url, limit=MAX_PAGES, scrape_options={"formats": ["markdown"]})
    )

    pages = []
    for doc in result.get("data") or []:
        text = doc.get("markdown") or ""
        if text.strip():
            metadata = doc.get("metadata") or {}
            pages.append(
                PageContent(
                    url=metadata.get("source_url", url),
                    title=metadata.get("og_title") or metadata.get("title") or url,
                    text=text,
                )
            )

    return CrawlResult(
        pages=pages,
        total_pages=len(pages),
        duration_ms=int((time.time() - start_time) * 1000),
    )


async def crawl_site(
    url: str, on_progress: Callable[[str], None] | None = None
) -> CrawlResult:
    result = await _crawl_site_httpx(url, on_progress)
    total_words = sum(len(p.text.split()) for p in result.pages)
    if total_words < 100:
        result = await _crawl_site_firecrawl(url, on_progress)
    return result


def validate_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            return False
        if (
            hostname.startswith("192.168.")
            or hostname.startswith("10.")
            or hostname.startswith("172.")
        ):
            return False
        return True
    except Exception:
        return False
