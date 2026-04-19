from pydantic import BaseModel, ConfigDict


class CampaignData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    campaign_id: str
    campaign_name: str
    campaign_status: int
    campaign_is_evergreen: bool
    leads_count: int
    contacted_count: int
    bounced_count: int
    completed_count: int
    open_count: int
    reply_count: int
    link_click_count: int
    unsubscribed_count: int
    emails_sent_count: int
    new_leads_contacted_count: int
    total_opportunities: int
    total_opportunity_value: float


class ReportOutput(BaseModel):
    markdown: str
    campaign_id: str
    campaign_name: str
    metrics: dict[str, str]
