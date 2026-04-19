import httpx
from temporalio import activity

from src.config import get_settings
from src.models.campaign import CampaignData


INSTANTLY_ANALYTICS_URL = "https://api.instantly.ai/api/v2/campaigns/analytics"


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
