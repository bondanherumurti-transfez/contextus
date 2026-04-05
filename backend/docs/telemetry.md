# Observability Implementation Plan: Honeycomb + OpenTelemetry

## Overview
Implement distributed tracing for critical paths using OpenTelemetry with Honeycomb as the backend.

## Critical Areas to Monitor

| Area | File | Function | Key Metrics |
|------|------|----------|-------------|
| OpenRouter Chat | `llm.py:215` | `stream_chat_response` | model, tokens, latency |
| OpenRouter Profile | `llm.py:147` | `_call_profile_model` | model, temperature, retry_attempt |
| OpenRouter Brief | `llm.py:250` | `generate_lead_brief` | model, message_count |
| Firecrawl | `crawler.py:176` | `_crawl_site_firecrawl` | url, pages_found, fallback |
| httpx Crawl | `crawler.py:105` | `_crawl_site_httpx` | url, pages_found, duration_ms |
| Chat Endpoint | `chat.py:38` | `send_chat_message` | session_id, kb_id, response_length |

## Architecture

```
FastAPI Request
└── chat.request (span)
    ├── redis.get_session
    ├── redis.get_knowledge_base
    ├── llm.stream_chat (span)
    │   ├── retrieval.retrieve_chunks
    │   └── openrouter.chat (span)
    │       └── Attributes: model, tokens, stream=True
    └── redis.save_session
```

## Files to Create/Modify

### 1. Create: `backend/app/services/telemetry.py`
OpenTelemetry initialization with Honeycomb OTLP exporter.

### 2. Modify: `backend/requirements.txt`
Add:
```
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp>=1.20.0
opentelemetry-instrumentation-fastapi>=0.41b0
opentelemetry-instrumentation-httpx>=0.41b0
```

### 3. Modify: `backend/app/main.py`
- Import and call `init_telemetry()` in lifespan
- Call `instrument_app(app)` after app creation

### 4. Modify: `backend/app/services/llm.py`
- Add span around `stream_chat_response` with token counting
- Add span around `_call_profile_model`
- Add span around `generate_lead_brief`

### 5. Modify: `backend/app/services/crawler.py`
- Add span around `_crawl_site_httpx`
- Add span around `_crawl_site_firecrawl`
- Add span around `crawl_site` (parent)

### 6. Modify: `backend/app/routers/chat.py`
- Add end-to-end span for `send_chat_message`

### 7. Modify: `backend/.env.example`
Add Honeycomb environment variables.

## Environment Variables

```
HONEYCOMB_API_KEY=your_key_here
OTEL_SERVICE_NAME=contextus-api
```

## Sampling
- 100% sampling (all traces sent)
- Honeycomb free tier: 20M events/month

## Token Counting
- Count tokens from streaming chunks (approximate, chunks ~= tokens)
- Add as `tokens_generated` attribute on span

## Honeycomb Queries
```sql
-- Average latency by model
AVG(duration_ms) GROUP BY model

-- Slow requests
COUNT() WHERE duration_ms > 3000

-- Token usage by customer
AVG(tokens_generated) GROUP BY kb_id

-- Latency heatmap
HEATMAP(duration_ms)
```
