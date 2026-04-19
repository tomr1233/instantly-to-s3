from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.activities.instantly import fetch_campaigns
    from src.activities.report import generate_report
    from src.activities.s3 import upload_to_s3
    from src.models.campaign import CampaignData, ReportOutput


FETCH_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
    maximum_attempts=3,
)

REPORT_RETRY = RetryPolicy(maximum_attempts=1)

UPLOAD_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
    maximum_attempts=3,
)


@workflow.defn
class InstantlyToS3Workflow:
    @workflow.run
    async def run(self) -> None:
        campaigns: list[CampaignData] = await workflow.execute_activity(
            fetch_campaigns,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=FETCH_RETRY,
        )

        run_date = workflow.now().strftime("%Y-%m-%d")
        workflow.logger.info(
            "fetched %d campaigns for run_date=%s", len(campaigns), run_date
        )

        for campaign in campaigns:
            try:
                report: ReportOutput = await workflow.execute_activity(
                    generate_report,
                    campaign,
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=REPORT_RETRY,
                )
                key = (
                    f"campaigns/instantly-campaigns/"
                    f"{report.campaign_name} {run_date}.md"
                )
                await workflow.execute_activity(
                    upload_to_s3,
                    args=[report.markdown, key],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=UPLOAD_RETRY,
                )
                workflow.logger.info(
                    "uploaded report for campaign_id=%s key=%s",
                    report.campaign_id,
                    key,
                )
            except Exception as exc:  # noqa: BLE001
                workflow.logger.exception(
                    "failed to process campaign_id=%s name=%s: %s",
                    campaign.campaign_id,
                    campaign.campaign_name,
                    exc,
                )
