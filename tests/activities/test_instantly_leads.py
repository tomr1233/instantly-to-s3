import json

import httpx
import pytest
import respx

from src.activities.instantly import fetch_leads


LEADS_URL = "https://api.instantly.ai/api/v2/leads/list"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")


def single_page_payload() -> dict:
    return {
        "items": [
            {"id": "lead_1", "email": "a@example.com"},
            {"id": "lead_2", "email": "b@example.com"},
        ],
        "next_starting_after": None,
    }


@respx.mock
async def test_fetch_leads_returns_serialized_payload_single_page():
    route = respx.post(LEADS_URL).mock(
        return_value=httpx.Response(200, json=single_page_payload())
    )

    payload = await fetch_leads("camp_123")

    assert route.called
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body == {"campaign": "camp_123", "limit": 100}

    assert payload.lead_count == 2
    leads = json.loads(payload.leads_json)
    assert leads == single_page_payload()["items"]
