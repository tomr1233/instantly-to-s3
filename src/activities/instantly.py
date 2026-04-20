import json

import httpx
from temporalio import activity

from src.config import get_settings
from src.models.campaign import CampaignData, LeadsPayload


INSTANTLY_ANALYTICS_URL = "https://api.instantly.ai/api/v2/campaigns/analytics"
INSTANTLY_LEADS_URL = "https://api.instantly.ai/api/v2/leads/list"


@activity.defn
async def fetch_campaigns() -> list[CampaignData]:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.instantly_api_key}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(INSTANTLY_ANALYTICS_URL, headers=headers)
        response.raise_for_status()

    payload = response.json()
    raw_list = payload.get("body", [])
    return [CampaignData(**raw) for raw in raw_list]


@activity.defn
async def fetch_leads(campaign_id: str) -> LeadsPayload:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.instantly_api_key}"}

    collected: list[dict] = []
    cursor: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            body: dict = {"campaign": campaign_id, "limit": 100}
            if cursor is not None:
                body["starting_after"] = cursor

            response = await client.post(
                INSTANTLY_LEADS_URL, headers=headers, json=body
            )
            response.raise_for_status()
            page = response.json()
            collected.extend(page.get("items", []))

            cursor = page.get("next_starting_after")
            if not cursor:
                break

    return LeadsPayload(
        leads_json=json.dumps(collected),
        lead_count=len(collected),
    )
