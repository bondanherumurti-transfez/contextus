import os
import httpx

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
        await client.post(
            "https://api.notion.com/v1/pages",
            json=page,
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
