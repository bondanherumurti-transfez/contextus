import os
import logging
import httpx

logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_VERSION = "2022-06-28"


async def post_waitlist_to_notion(data: dict):
    database_id = os.getenv("NOTION_DB_WAITLIST", "")
    if not NOTION_TOKEN or not database_id:
        return

    def txt(val):
        return [{"text": {"content": str(val or "—")}}]

    page = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name":           {"title": txt(data.get("name", "Unknown"))},
            "Email":          {"email": data.get("email") or None},
            "Website":        {"url": data.get("website") or None},
            "Phone":          {"phone_number": data.get("phone") or None},
            "Business Type":  {"rich_text": txt(data.get("business_type"))},
            "Goal":           {"rich_text": txt(data.get("goal"))},
            "Agent Behavior": {"rich_text": txt(data.get("agent_behavior"))},
            "Timeline":       {"rich_text": txt(data.get("timeline"))},
            "Session":        {"rich_text": txt(data.get("session_id"))},
        },
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.notion.com/v1/pages",
            json=page,
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        if res.status_code != 200:
            logger.error("Notion waitlist post failed %s: %s", res.status_code, res.text)


async def post_lead_brief_to_notion(data: dict):
    """Post a lead brief to NOTION_DB_LEADS. Works for both organic and waitlist sessions."""
    database_id = os.getenv("NOTION_DB_LEADS", "")
    if not NOTION_TOKEN or not database_id:
        return

    def txt(val):
        return [{"text": {"content": str(val or "—")}}]

    contact = data.get("contact") or {}
    lead_type = "Waitlist" if data.get("is_waitlist") else "Organic"

    page = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name":               {"title": txt(data.get("who", "Unknown visitor"))},
            "Type":               {"select": {"name": lead_type}},
            "Need":               {"rich_text": txt(data.get("need"))},
            "Signals":            {"rich_text": txt(data.get("signals"))},
            "Open Questions":     {"rich_text": txt(data.get("open_questions"))},
            "Suggested Approach": {"rich_text": txt(data.get("suggested_approach"))},
            "Quality":            {"select": {"name": (data.get("quality_score") or "medium").capitalize()}},
            "Email":              {"email": contact.get("email") or data.get("email") or None},
            "Phone":              {"phone_number": contact.get("phone") or contact.get("whatsapp") or data.get("phone") or None},
            "Website":            {"url": data.get("website") or None},
            "Site KB":            {"rich_text": txt(data.get("kb_id"))},
            "Session":            {"rich_text": txt(data.get("session_id"))},
        },
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.notion.com/v1/pages",
            json=page,
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        if res.status_code != 200:
            logger.error("Notion lead brief post failed %s: %s", res.status_code, res.text)
            return False
        return True
