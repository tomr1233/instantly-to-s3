from temporalio.client import Client

from src.config import get_settings


async def connect() -> Client:
    settings = get_settings()
    return await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
