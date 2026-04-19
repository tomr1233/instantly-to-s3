import concurrent.futures
from datetime import datetime, timezone

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.models.campaign import CampaignData, ReportOutput
from src.workflows.campaign_sync import InstantlyToS3Workflow


def make_campaign(campaign_id: str, name: str) -> CampaignData:
    return CampaignData(
        campaign_id=campaign_id,
        campaign_name=name,
        campaign_status=1,
        campaign_is_evergreen=False,
        leads_count=10,
        contacted_count=10,
        bounced_count=0,
        completed_count=10,
        open_count=5,
        reply_count=1,
        link_click_count=2,
        unsubscribed_count=0,
        emails_sent_count=10,
        new_leads_contacted_count=10,
        total_opportunities=1,
        total_opportunity_value=100.0,
    )


class FakeState:
    def __init__(self, campaigns: list[CampaignData]):
        self.campaigns = campaigns
        self.uploads: list[tuple[str, str]] = []  # (key, content)
        self.fail_upload_for: set[str] = set()


@pytest.fixture
def fake_state() -> FakeState:
    return FakeState([make_campaign("c1", "Alpha"), make_campaign("c2", "Beta")])


def build_fake_activities(state: FakeState):
    @activity.defn(name="fetch_campaigns")
    async def fetch_campaigns() -> list[CampaignData]:
        return state.campaigns

    @activity.defn(name="generate_report")
    def generate_report(campaign: CampaignData) -> ReportOutput:
        return ReportOutput(
            markdown=f"# {campaign.campaign_name}",
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            metrics={},
        )

    @activity.defn(name="upload_to_s3")
    async def upload_to_s3(content: str, key: str) -> None:
        if any(bad in key for bad in state.fail_upload_for):
            raise RuntimeError(f"forced failure for {key}")
        state.uploads.append((key, content))

    return [fetch_campaigns, generate_report, upload_to_s3]


async def test_workflow_uploads_one_report_per_campaign(fake_state):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-q",
            workflows=[InstantlyToS3Workflow],
            activities=build_fake_activities(fake_state),
            activity_executor=concurrent.futures.ThreadPoolExecutor(),
        ):
            await env.client.execute_workflow(
                InstantlyToS3Workflow.run,
                id="wf-1",
                task_queue="test-q",
            )

    assert len(fake_state.uploads) == 2
    keys = {key for key, _ in fake_state.uploads}
    assert any("Alpha" in k for k in keys)
    assert any("Beta" in k for k in keys)


async def test_workflow_s3_key_format(fake_state):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-q",
            workflows=[InstantlyToS3Workflow],
            activities=build_fake_activities(fake_state),
            activity_executor=concurrent.futures.ThreadPoolExecutor(),
        ):
            await env.client.execute_workflow(
                InstantlyToS3Workflow.run,
                id="wf-2",
                task_queue="test-q",
            )

    for key, _ in fake_state.uploads:
        assert key.startswith("campaigns/instantly-campaigns/")
        assert key.endswith(".md")
        # format: campaigns/instantly-campaigns/{name} {YYYY-MM-DD}.md
        stem = key.removeprefix("campaigns/instantly-campaigns/").removesuffix(".md")
        name_part, date_part = stem.rsplit(" ", 1)
        datetime.strptime(date_part, "%Y-%m-%d")  # raises if malformed
        assert name_part in {"Alpha", "Beta"}


async def test_workflow_continues_when_one_campaign_fails(fake_state):
    fake_state.fail_upload_for = {"Alpha"}
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-q",
            workflows=[InstantlyToS3Workflow],
            activities=build_fake_activities(fake_state),
            activity_executor=concurrent.futures.ThreadPoolExecutor(),
        ):
            await env.client.execute_workflow(
                InstantlyToS3Workflow.run,
                id="wf-3",
                task_queue="test-q",
            )

    uploaded_names = {k.split("/")[-1].split(" ")[0] for k, _ in fake_state.uploads}
    assert "Beta" in uploaded_names
    assert "Alpha" not in uploaded_names
