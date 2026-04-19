from fastapi import FastAPI

from src.api.routes.workflows import build_router
from src.temporal_client import connect


async def get_temporal_client():
    return await connect()


app = FastAPI(title="instantly-to-s3")
app.include_router(build_router(get_temporal_client))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
