import pytest
from pydantic import ValidationError

from src.models.campaign import CampaignData, ReportOutput


def sample_campaign_dict() -> dict:
    return {
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
        "total_opportunity_value": 12500.50,
    }


def test_campaign_data_parses_valid_payload():
    data = CampaignData(**sample_campaign_dict())
    assert data.campaign_id == "camp_123"
    assert data.campaign_name == "Spring Outreach"
    assert data.leads_count == 1000
    assert data.total_opportunity_value == 12500.50


def test_campaign_data_rejects_missing_required_field():
    payload = sample_campaign_dict()
    del payload["campaign_id"]
    with pytest.raises(ValidationError):
        CampaignData(**payload)


def test_campaign_data_ignores_unknown_fields():
    payload = sample_campaign_dict()
    payload["unknown_extra_field"] = "ignored"
    data = CampaignData(**payload)
    assert data.campaign_id == "camp_123"


def test_report_output_fields():
    out = ReportOutput(
        markdown="# Report",
        campaign_id="camp_123",
        campaign_name="Spring Outreach",
        metrics={"delivery_rate": "97.8%"},
    )
    assert out.markdown == "# Report"
    assert out.metrics["delivery_rate"] == "97.8%"
