from src.activities.report import generate_report
from src.models.campaign import CampaignData


def healthy_campaign() -> CampaignData:
    return CampaignData(
        campaign_id="camp_123",
        campaign_name="Spring Outreach",
        campaign_status=1,
        campaign_is_evergreen=False,
        leads_count=1000,
        contacted_count=900,
        bounced_count=20,
        completed_count=800,
        open_count=400,
        reply_count=50,
        link_click_count=100,
        unsubscribed_count=5,
        emails_sent_count=900,
        new_leads_contacted_count=850,
        total_opportunities=10,
        total_opportunity_value=12500.50,
    )


def test_generate_report_returns_report_output():
    result = generate_report(healthy_campaign())
    assert result.campaign_id == "camp_123"
    assert result.campaign_name == "Spring Outreach"
    assert isinstance(result.markdown, str)
    assert len(result.markdown) > 0


def test_generate_report_markdown_contains_required_sections():
    md = generate_report(healthy_campaign()).markdown
    assert "# Campaign Report: Spring Outreach" in md
    assert "## Overview" in md
    assert "## Outreach Summary" in md
    assert "## Engagement Metrics" in md
    assert "## Email Activity" in md
    assert "## Opportunity Tracking" in md
    assert "## KPI Health" in md
    assert "## Recommendations" in md


def test_generate_report_computes_rates():
    result = generate_report(healthy_campaign())
    # delivery = (contacted - bounced) / contacted = 880/900 = 97.78%
    assert result.metrics["delivery_rate"] == "97.78%"
    # reply = reply / contacted = 50/900 = 5.56%
    assert result.metrics["reply_rate"] == "5.56%"
    # bounce = bounced / contacted = 20/900 = 2.22%
    assert result.metrics["bounce_rate"] == "2.22%"


def test_generate_report_handles_zero_contacted():
    campaign = healthy_campaign()
    campaign.contacted_count = 0
    campaign.bounced_count = 0
    result = generate_report(campaign)
    assert result.metrics["delivery_rate"] == "0.00%"
    assert result.metrics["reply_rate"] == "0.00%"
    assert result.metrics["bounce_rate"] == "0.00%"


def test_generate_report_recommends_action_when_bounce_high():
    campaign = healthy_campaign()
    campaign.bounced_count = 200  # > 5% → high bounce
    md = generate_report(campaign).markdown
    assert "bounce rate" in md.lower()


def test_generate_report_recommends_action_when_reply_low():
    campaign = healthy_campaign()
    campaign.reply_count = 1  # very low reply
    md = generate_report(campaign).markdown
    assert "reply rate" in md.lower()
