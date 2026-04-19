import uuid

from fastapi import APIRouter, Depends, status

from src.config import get_settings
from src.workflows.campaign_sync import InstantlyToS3Workflow


def build_router(get_client_dep) -> APIRouter:
    router = APIRouter()

    @router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
    async def trigger(client=Depends(get_client_dep)) -> dict[str, str]:
        settings = get_settings()
        workflow_id = f"instantly-to-s3-manual-{uuid.uuid4().hex[:8]}"
        handle = await client.start_workflow(
            InstantlyToS3Workflow.run,
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
        )
        return {"workflow_id": handle.id}

    return router
