import os
import logging

logger = logging.getLogger(__name__)

_client = None


def init_amplitude():
    global _client
    api_key = os.getenv("AMPLITUDE_API_KEY", "")
    if not api_key:
        logger.warning("AMPLITUDE_API_KEY not set — analytics disabled")
        return
    try:
        from amplitude import Amplitude
        _client = Amplitude(api_key)
        logger.info("Amplitude analytics initialized")
    except Exception:
        logger.exception("Failed to initialize Amplitude")


def shutdown_amplitude():
    global _client
    if _client:
        try:
            _client.shutdown()
        except Exception:
            logger.exception("Failed to shutdown Amplitude")


def track(event_type: str, kb_id: str, session_id: str | None = None, properties: dict | None = None):
    if not _client:
        return
    # Amplitude requires user_id and device_id to be at least 5 characters
    if not kb_id or len(kb_id) < 5:
        logger.warning("Amplitude: skipping event=%s — kb_id too short (%r)", event_type, kb_id)
        return
    try:
        from amplitude import BaseEvent
        props = dict(properties or {})
        if session_id:
            props.setdefault("session_id", session_id)
        _client.track(BaseEvent(
            event_type=event_type,
            user_id=kb_id,
            # only set device_id when session_id meets the 5-char minimum
            device_id=session_id if session_id and len(session_id) >= 5 else None,
            event_properties=props,
        ))
    except Exception:
        logger.exception("Amplitude track failed: event=%s kb_id=%s", event_type, kb_id)
