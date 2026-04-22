from pydantic import BaseModel
from typing import Literal


class PillSuggestions(BaseModel):
    service_questions: list[str] = []
    gap_questions: list[str] = []
    industry_questions: list[str] = []


class CompanyProfile(BaseModel):
    name: str
    industry: str
    services: list[str]
    out_of_scope: list[str] = []
    location: str | None = None
    contact: dict | None = None
    summary: str
    gaps: list[str]
    pill_suggestions: PillSuggestions | None = None
    language: str = "en"


class Chunk(BaseModel):
    id: str
    source: str
    text: str
    word_count: int


class KnowledgeBase(BaseModel):
    job_id: str
    status: Literal["crawling", "analyzing", "complete", "failed"]
    progress: str = ""
    pages_found: int = 0
    quality_tier: Literal["rich", "thin", "empty"] | None = None
    company_profile: CompanyProfile | None = None
    chunks: list[Chunk] = []
    suggested_pills: list[str] = []
    language: str = "en"
    created_at: int


class Message(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    timestamp: int


class Session(BaseModel):
    session_id: str
    kb_id: str
    messages: list[Message] = []
    contact_captured: bool = False
    contact_value: str | None = None
    brief_sent: bool = False
    created_at: int


class LeadBrief(BaseModel):
    session_id: str
    created_at: str
    who: str
    need: str
    signals: str
    open_questions: str
    suggested_approach: str
    quality_score: Literal["high", "medium", "low"]
    qualification: Literal["qualified", "out_of_scope", "unclear", "suspicious"] = "unclear"
    qualification_reason: str = ""
    scope_match: Literal["true", "false", "unclear"] = "unclear"
    red_flags: list[str] = []
    contact: dict | None = None
    metadata: dict


class CrawlRequest(BaseModel):
    url: str
    cf_turnstile_response: str | None = None


class CrawlResponse(BaseModel):
    job_id: str
    status: str


class EnrichRequest(BaseModel):
    answers: dict[str, str]


class UpdatePillsRequest(BaseModel):
    pills: list[str]


class SessionRequest(BaseModel):
    knowledge_base_id: str


class SessionResponse(BaseModel):
    session_id: str
    pills: list[str] = []
    language: str = "en"
    name: str = ""


class ChatRequest(BaseModel):
    message: str
