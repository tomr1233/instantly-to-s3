from temporalio import activity

from src.models.campaign import CampaignData, ReportOutput


def _pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00%"
    return f"{(numerator / denominator) * 100:.2f}%"


def _status_label(status: int) -> str:
    return {
        0: "Draft",
        1: "Active",
        2: "Paused",
        3: "Completed",
        4: "Running Subsequences",
        -99: "Account Suspended",
        -1: "Accounts Unhealthy",
        -2: "Bounce Protect",
    }.get(status, f"Unknown ({status})")


def _compute_metrics(c: CampaignData) -> dict[str, str]:
    delivered = max(c.contacted_count - c.bounced_count, 0)
    return {
        "delivery_rate": _pct(delivered, c.contacted_count),
        "reply_rate": _pct(c.reply_count, c.contacted_count),
        "bounce_rate": _pct(c.bounced_count, c.contacted_count),
        "open_rate": _pct(c.open_count, c.contacted_count),
        "click_rate": _pct(c.link_click_count, c.contacted_count),
        "unsubscribe_rate": _pct(c.unsubscribed_count, c.contacted_count),
    }


def _recommendations(c: CampaignData, metrics: dict[str, str]) -> list[str]:
    recs: list[str] = []
    bounce_pct = float(metrics["bounce_rate"].rstrip("%"))
    reply_pct = float(metrics["reply_rate"].rstrip("%"))
    open_pct = float(metrics["open_rate"].rstrip("%"))

    if bounce_pct > 5:
        recs.append(
            f"High bounce rate ({metrics['bounce_rate']}). "
            "Clean the lead list and verify email deliverability."
        )
    if reply_pct < 2 and c.contacted_count > 100:
        recs.append(
            f"Low reply rate ({metrics['reply_rate']}). "
            "Review copy, subject lines, and targeting."
        )
    if open_pct < 30 and c.contacted_count > 100:
        recs.append(
            f"Low open rate ({metrics['open_rate']}). "
            "Test alternative subject lines and sending times."
        )
    if not recs:
        recs.append("Metrics are within healthy ranges. Maintain current approach.")
    return recs


def _render_markdown(c: CampaignData, metrics: dict[str, str]) -> str:
    delivered = max(c.contacted_count - c.bounced_count, 0)
    recs = _recommendations(c, metrics)
    recs_md = "\n".join(f"- {r}" for r in recs)
    evergreen = "Yes" if c.campaign_is_evergreen else "No"

    return f"""# Campaign Report: {c.campaign_name}

## Overview

| Field | Value |
|---|---|
| Campaign ID | `{c.campaign_id}` |
| Name | {c.campaign_name} |
| Status | {_status_label(c.campaign_status)} |
| Evergreen | {evergreen} |

## Outreach Summary

| Metric | Count |
|---|---|
| Total leads | {c.leads_count} |
| Contacted | {c.contacted_count} |
| Delivered | {delivered} |
| Bounced | {c.bounced_count} |
| Completed | {c.completed_count} |

## Engagement Metrics

| Metric | Count |
|---|---|
| Opens | {c.open_count} |
| Replies | {c.reply_count} |
| Link clicks | {c.link_click_count} |
| Unsubscribes | {c.unsubscribed_count} |

## Email Activity

| Metric | Count |
|---|---|
| Emails sent | {c.emails_sent_count} |
| New leads contacted | {c.new_leads_contacted_count} |

## Opportunity Tracking

| Metric | Value |
|---|---|
| Opportunities | {c.total_opportunities} |
| Opportunity value | ${c.total_opportunity_value:,.2f} |

## KPI Health

| KPI | Rate |
|---|---|
| Delivery rate | {metrics['delivery_rate']} |
| Open rate | {metrics['open_rate']} |
| Reply rate | {metrics['reply_rate']} |
| Click rate | {metrics['click_rate']} |
| Bounce rate | {metrics['bounce_rate']} |
| Unsubscribe rate | {metrics['unsubscribe_rate']} |

## Recommendations

{recs_md}
"""


@activity.defn
def generate_report(campaign: CampaignData) -> ReportOutput:
    metrics = _compute_metrics(campaign)
    return ReportOutput(
        markdown=_render_markdown(campaign, metrics),
        campaign_id=campaign.campaign_id,
        campaign_name=campaign.campaign_name,
        metrics=metrics,
    )
