# Instantly to S3 — Campaign Analytics Sync

## Purpose

Replaces the n8n "Move campaigns from instantly to s3" workflow with a Temporal-based system. Runs weekly, fetches campaign analytics from the Instantly API, generates a markdown report per campaign, and uploads each report to S3.

## Architecture

```
Temporal Schedule (weekly cron)
  -> starts InstantlyToS3Workflow
    -> Activity: fetch_campaigns (GET Instantly API)
    -> For each campaign:
        -> Activity: generate_report (build markdown string)
        -> Activity: upload_to_s3 (put markdown file to S3)
```

No RabbitMQ — single system with no service-to-service messaging needed.

## Project Structure

```
instantly-to-s3/
├── src/
│   ├── api/
│   │   ├── main.py          # FastAPI app (health check, manual trigger)
│   │   └── routes/
│   │       └── workflows.py  # POST /trigger endpoint for manual runs
│   ├── workflows/
│   │   └── campaign_sync.py  # Workflow definition
│   ├── activities/
│   │   ├── instantly.py      # fetch_campaigns()
│   │   ├── report.py         # generate_report()
│   │   └── s3.py             # upload_to_s3()
│   └── models/
│       └── campaign.py       # Pydantic models
├── worker.py                 # Temporal worker entry point
├── tests/
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Workflow: `InstantlyToS3Workflow`

**Trigger:** Temporal schedule, runs weekly on Mondays at 00:00 UTC. Schedule is created on worker startup via Temporal's schedule API (idempotent — updates if already exists).

**Steps:**

1. Execute `fetch_campaigns` activity — calls `GET https://api.instantly.ai/api/v2/campaigns/analytics` with bearer token auth. The activity parses the response `body` array and returns `list[CampaignData]`.
2. For each campaign in the list:
   a. Execute `generate_report` activity — takes `CampaignData`, returns markdown string + campaign metadata.
   b. Build the S3 key in the workflow: `campaigns/instantly-campaigns/{campaign_name} {YYYY-MM-DD}.md` (date from workflow start time via `workflow.now()` to stay deterministic).
   c. Execute `upload_to_s3` activity — uploads the markdown string as a `.md` file to S3.

Each campaign iteration is independent. If one campaign fails after retries, the workflow logs the error and continues to the next campaign.

**Re-runs:** If the workflow runs twice on the same day (manual trigger + schedule), the second run overwrites the same S3 keys. This is acceptable — markdown reports are regenerable and overwriting is idempotent.

## Activities

### `fetch_campaigns`

- **Input:** None (reads `INSTANTLY_API_KEY` from environment)
- **Output:** `list[CampaignData]`
- **Side effects:** HTTP GET to Instantly API
- **Retry policy:** 3 attempts, backoff

### `generate_report`

- **Input:** `CampaignData`
- **Output:** `ReportOutput` (markdown string, campaign_id, campaign_name, computed metrics dict)
- **Side effects:** None — pure data transformation
- **Retry policy:** 1 attempt (deterministic, no reason to retry)

The markdown report includes:
- Campaign overview (name, ID, status, type)
- Outreach summary table (leads, contacted, delivered, bounced, completed)
- Engagement metrics table (opens, replies, link clicks, unsubscribes)
- Email activity stats
- Opportunity tracking table
- KPI health score (delivery rate, reply rate, bounce rate)
- Recommendations based on metric thresholds

This is a direct port of the n8n Code node logic.

### `upload_to_s3`

- **Input:** markdown content (str), S3 object key (str) — key is built by the workflow and passed in
- **Output:** None
- **Side effects:** PUT object to S3
- **Retry policy:** 3 attempts, backoff

**S3 path format:** `campaigns/instantly-campaigns/{campaign_name} {YYYY-MM-DD}.md` (built in the workflow using the deterministic workflow start time)

**Bucket:** `expressnext-workspace`

**Content type:** `text/markdown`

## Models

### `CampaignData`

Pydantic model matching the Instantly API response fields:

- `campaign_id: str`
- `campaign_name: str`
- `campaign_status: int`
- `campaign_is_evergreen: bool`
- `leads_count: int`
- `contacted_count: int`
- `bounced_count: int`
- `completed_count: int`
- `open_count: int`
- `reply_count: int`
- `link_click_count: int`
- `unsubscribed_count: int`
- `emails_sent_count: int`
- `new_leads_contacted_count: int`
- `total_opportunities: int`
- `total_opportunity_value: float`

### `ReportOutput`

- `markdown: str`
- `campaign_id: str`
- `campaign_name: str`
- `metrics: dict` (computed rates as strings)

## Configuration

All via environment variables:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `INSTANTLY_API_KEY` | Yes | — | Bearer token for Instantly API |
| `AWS_ACCESS_KEY_ID` | Yes | — | S3 upload auth |
| `AWS_SECRET_ACCESS_KEY` | Yes | — | S3 upload auth |
| `AWS_REGION` | No | `ap-southeast-2` | S3 bucket region |
| `S3_BUCKET_NAME` | No | `expressnext-workspace` | Target bucket |
| `TEMPORAL_HOST` | No | `localhost:7233` | Temporal server address |

## FastAPI Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/trigger` | Manually trigger the workflow (bypasses schedule) |

The API layer is thin — it only starts Temporal workflows.

## Error Handling

- Temporal's built-in retry handles transient failures (API timeouts, S3 errors)
- Each campaign processes independently — one failure doesn't block others
- Failed campaigns are logged with campaign ID and error detail
- No dead letter queue needed — Temporal provides full visibility into failed workflow runs

## Local Development

`docker-compose.yml` runs:
- Temporal server + UI
- FastAPI app
- Temporal worker

## What's Not Included

- Docx conversion (removed — markdown uploaded directly)
- RabbitMQ (no inter-service messaging)
- Shared pip package (single system, no shared code needed yet)
