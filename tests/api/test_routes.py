import os

os.environ.setdefault("INSTANTLY_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.main import app, get_temporal_client


def test_health_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trigger_starts_workflow():
    fake_handle = MagicMock()
    fake_handle.id = "instantly-to-s3-manual-abc"
    fake_client = MagicMock()
    fake_client.start_workflow = AsyncMock(return_value=fake_handle)

    app.dependency_overrides[get_temporal_client] = lambda: fake_client
    try:
        with TestClient(app) as client:
            response = client.post("/trigger")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["workflow_id"] == "instantly-to-s3-manual-abc"
    fake_client.start_workflow.assert_awaited_once()
