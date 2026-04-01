"""
Shared fixtures for e2e tests.

Starts a real uvicorn server as a subprocess before the test session,
tears it down after. Tests hit it over actual HTTP.
"""

import subprocess
import time
import sys
import os
import pytest
import httpx

E2E_PORT = 8001
E2E_BASE_URL = f"http://localhost:{E2E_PORT}"
RATE_LIMIT_KEY = "rate:127.0.0.1:crawl"


@pytest.fixture(scope="session")
def server():
    """
    Spin up a real uvicorn server for the entire test session.
    Waits until the health endpoint responds before yielding.
    Kills the process after all tests complete.
    """
    env = os.environ.copy()
    env["PORT"] = str(E2E_PORT)

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(E2E_PORT), "--log-level", "error"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Poll health endpoint until server is ready (max 10s)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            r = httpx.get(f"{E2E_BASE_URL}/api/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("Server did not start within 10 seconds")

    yield E2E_BASE_URL

    process.terminate()
    process.wait()


@pytest.fixture(autouse=False, scope="module")
def clear_crawl_rate_limit():
    """
    Reset the crawl rate limit key in Redis before a test.
    Use on fixtures/tests that need to submit real crawl jobs
    without being blocked by prior test runs.
    """
    from dotenv import load_dotenv
    load_dotenv()
    from upstash_redis import Redis
    r = Redis(url=os.getenv("UPSTASH_REDIS_REST_URL"), token=os.getenv("UPSTASH_REDIS_REST_TOKEN"))
    r.delete(RATE_LIMIT_KEY)
    yield
