# instantly-to-s3

Weekly sync of Instantly campaign analytics to S3 as markdown reports. Temporal-based replacement for the n8n "Move campaigns from instantly to s3" workflow.

## How it works

1. Temporal schedule `instantly-to-s3-weekly` fires every Monday 00:00 UTC.
2. `InstantlyToS3Workflow` calls `fetch_campaigns` (GET Instantly analytics API).
3. For each campaign: `generate_report` → markdown string, then `upload_to_s3` → `campaigns/instantly-campaigns/{campaign_name} {YYYY-MM-DD}.md`.

Per-campaign iterations are independent: a single failure is logged and the workflow continues.

## Local development

```bash
cp .env.example .env
# fill in secrets
docker compose up --build
```

- API:         http://localhost:8000
- Temporal UI: http://localhost:8080

## Manual trigger

```bash
curl -X POST http://localhost:8000/trigger
```

Returns `{"workflow_id": "instantly-to-s3-manual-XXXXXXXX"}`. Tail the run in the Temporal UI.

## Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Configuration

See `.env.example` for all variables. Defaults:
- `AWS_REGION=ap-southeast-2`
- `S3_BUCKET_NAME=expressnext-workspace`
- `TEMPORAL_HOST=localhost:7233`
- `TEMPORAL_TASK_QUEUE=instantly-to-s3`
