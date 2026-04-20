import asyncio
import concurrent.futures
import logging

from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleSpec,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.worker import Worker

from src.activities.instantly import fetch_campaigns
from src.activities.report import generate_report
from src.activities.s3 import upload_to_s3
from src.config import get_settings
from src.temporal_client import connect
from src.workflows.campaign_sync import InstantlyToS3Workflow


SCHEDULE_ID = "instantly-to-s3-weekly"
WORKFLOW_ID = "instantly-to-s3"

logger = logging.getLogger(__name__)


def build_schedule_spec() -> ScheduleSpec:
    # Every Monday at 00:00 UTC.
    return ScheduleSpec(cron_expressions=["0 0 * * 1"])


async def ensure_schedule(client) -> None:
    settings = get_settings()
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            InstantlyToS3Workflow.run,
            id=WORKFLOW_ID,
            task_queue=settings.temporal_task_queue,
        ),
        spec=build_schedule_spec(),
    )
    try:
        await client.create_schedule(SCHEDULE_ID, schedule)
        logger.info("created schedule %s", SCHEDULE_ID)
    except ScheduleAlreadyRunningError:
        handle = client.get_schedule_handle(SCHEDULE_ID)

        def updater(input: ScheduleUpdateInput) -> ScheduleUpdate:
            return ScheduleUpdate(
                schedule=Schedule(
                    action=schedule.action,
                    spec=schedule.spec,
                )
            )

        await handle.update(updater)
        logger.info("updated existing schedule %s", SCHEDULE_ID)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    client = await connect()

    await ensure_schedule(client)

    with concurrent.futures.ThreadPoolExecutor() as activity_executor:
        async with Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[InstantlyToS3Workflow],
            activities=[fetch_campaigns, generate_report, upload_to_s3],
            activity_executor=activity_executor,
        ):
            logger.info("worker listening on task_queue=%s", settings.temporal_task_queue)
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
