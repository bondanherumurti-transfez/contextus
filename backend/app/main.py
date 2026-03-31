import truststore
truststore.inject_into_ssl()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.routers import crawl, session, chat, brief

load_dotenv()

app = FastAPI(
    title="contextus API",
    description="Backend API for contextus - AI-powered chat widget for SMBs",
    version="1.0.0",
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


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
