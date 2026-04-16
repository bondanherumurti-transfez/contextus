import logging
from fastapi import APIRouter
from pydantic import BaseModel

from app.services import analytics

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)


class EventRequest(BaseModel):
    name: str
    kb_id: str
    session_id: str | None = None
    source_domain: str | None = None
    source_type: str | None = None
    label: str | None = None
    index: int | None = None
    source: str | None = None


@router.post("/events", status_code=202)
async def track_widget_event(body: EventRequest):
    """
    Receives UI-only events from the widget (fab_open, fab_close, pill_click)
    that have no server-side equivalent, and forwards them to Amplitude.
    Returns 202 immediately — fire-and-forget from the widget's perspective.
    """
    properties = {
        "source_domain": body.source_domain or "",
        "source_type": body.source_type or "tenant",
    }
    if body.label is not None:
        properties["label"] = body.label
    if body.index is not None:
        properties["index"] = body.index
    if body.source is not None:
        properties["source"] = body.source
    analytics.track(
        event_type=body.name,
        kb_id=body.kb_id,
        session_id=body.session_id,
        properties=properties,
    )
    logger.debug("track_widget_event: name=%s kb_id=%s domain=%s", body.name, body.kb_id, body.source_domain)
    return {"ok": True}
