import truststore
truststore.inject_into_ssl()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
import os

from app.routers import crawl, session, chat, brief, waitlist, jobs
from app.services.database import init_db

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[startup] Running init_db...")
    try:
        await init_db()
        logger.info("[startup] init_db complete")
    except Exception as e:
        logger.error("[startup] init_db failed: %s — continuing without Neon", e)
    yield
    logger.info("[shutdown] App shutting down")


app = FastAPI(
    title="contextus API",
    description="Backend API for contextus - AI-powered chat widget for SMBs",
    version="1.0.0",
    lifespan=lifespan,
)

allowed_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:8000,http://localhost:3000"
).split(",")

allowed_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX", "")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crawl.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(brief.router, prefix="/api")
app.include_router(waitlist.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
