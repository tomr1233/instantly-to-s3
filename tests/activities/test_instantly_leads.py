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


@respx.mock
async def test_fetch_leads_paginates_until_cursor_is_none():
    page1 = {
        "items": [{"id": "lead_1"}, {"id": "lead_2"}],
        "next_starting_after": "cursor_abc",
    }
    page2 = {
        "items": [{"id": "lead_3"}],
        "next_starting_after": None,
    }
    responses = [httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    route = respx.post(LEADS_URL).mock(side_effect=responses)

    payload = await fetch_leads("camp_xyz")

    assert route.call_count == 2
    first_body = json.loads(route.calls[0].request.content)
    second_body = json.loads(route.calls[1].request.content)
    assert first_body == {"campaign": "camp_xyz", "limit": 100}
    assert second_body == {
        "campaign": "camp_xyz",
        "limit": 100,
        "starting_after": "cursor_abc",
    }

    assert payload.lead_count == 3
    leads = json.loads(payload.leads_json)
    assert [lead["id"] for lead in leads] == ["lead_1", "lead_2", "lead_3"]


@respx.mock
async def test_fetch_leads_raises_when_page_cap_exceeded(monkeypatch):
    import src.activities.instantly as module

    monkeypatch.setattr(module, "MAX_LEADS_PAGES", 2)

    responses = [
        httpx.Response(200, json={"items": [{"id": "x"}], "next_starting_after": "c1"}),
        httpx.Response(200, json={"items": [{"id": "y"}], "next_starting_after": "c2"}),
    ]
    respx.post(LEADS_URL).mock(side_effect=responses)

    with pytest.raises(RuntimeError, match="exceeded 2 pages"):
        await fetch_leads("camp_runaway")


@respx.mock
async def test_fetch_leads_empty_items():
    respx.post(LEADS_URL).mock(
        return_value=httpx.Response(
            200, json={"items": [], "next_starting_after": None}
        )
    )

    payload = await fetch_leads("camp_empty")

    assert payload.lead_count == 0
    assert payload.leads_json == "[]"


@respx.mock
async def test_fetch_leads_raises_on_http_error():
    respx.post(LEADS_URL).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_leads("camp_err")
