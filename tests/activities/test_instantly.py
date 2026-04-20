import httpx
import pytest
import respx

from src.activities.instantly import fetch_campaigns


INSTANTLY_URL = "https://api.instantly.ai/api/v2/campaigns/analytics"


def sample_api_payload() -> list:
    return [
        {
            "campaign_id": "camp_123",
            "campaign_name": "Spring Outreach",
            "campaign_status": 1,
            "campaign_is_evergreen": False,
            "leads_count": 1000,
            "contacted_count": 900,
            "bounced_count": 20,
            "completed_count": 800,
            "open_count": 400,
            "reply_count": 50,
            "link_click_count": 100,
            "unsubscribed_count": 5,
            "emails_sent_count": 900,
            "new_leads_contacted_count": 850,
            "total_opportunities": 10,
            "total_opportunity_value": 12500.5,
        }
    ]


@respx.mock
async def test_fetch_campaigns_returns_campaign_list(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    route = respx.get(INSTANTLY_URL).mock(
        return_value=httpx.Response(200, json=sample_api_payload())
    )

    campaigns = await fetch_campaigns()

    assert route.called
    assert route.calls.last.request.headers["authorization"] == "Bearer test-key"
    assert len(campaigns) == 1
    assert campaigns[0].campaign_id == "camp_123"
    assert campaigns[0].campaign_name == "Spring Outreach"


@respx.mock
async def test_fetch_campaigns_empty_body(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    respx.get(INSTANTLY_URL).mock(return_value=httpx.Response(200, json=[]))
    campaigns = await fetch_campaigns()
    assert campaigns == []


@respx.mock
async def test_fetch_campaigns_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    respx.get(INSTANTLY_URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_campaigns()


@respx.mock
async def test_fetch_campaigns_passes_bearer_auth(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "my-secret")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    route = respx.get(INSTANTLY_URL).mock(
        return_value=httpx.Response(200, json=[])
    )
    await fetch_campaigns()
    assert route.calls.last.request.headers["authorization"] == "Bearer my-secret"
