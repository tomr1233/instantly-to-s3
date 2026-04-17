# Instantly to S3 — Campaign Analytics Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Temporal-based Python system that weekly fetches campaign analytics from the Instantly API, renders a markdown report per campaign, and uploads each report to S3. Replaces an existing n8n workflow.

**Architecture:** FastAPI (thin trigger layer) + Temporal (workflow engine) + Temporal worker (runs workflow + activities). One workflow `InstantlyToS3Workflow` orchestrates three activities (`fetch_campaigns`, `generate_report`, `upload_to_s3`). Scheduled weekly via Temporal's schedule API, created idempotently on worker startup.

**Tech Stack:** Python 3.11+, `temporalio` (Temporal Python SDK), `fastapi`, `uvicorn`, `httpx` (Instantly API), `boto3` (S3), `pydantic` v2, `pytest` + `pytest-asyncio`. Local dev via `docker-compose` with Temporal server + UI.

**Spec:** `docs/superpowers/specs/2026-04-14-instantly-to-s3-design.md`

---

## File Structure (locked in before task decomposition)

```
instantly-to-s3/
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app factory + /health
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── workflows.py        # POST /trigger
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── campaign_sync.py        # InstantlyToS3Workflow
│   ├── activities/
│   │   ├── __init__.py
│   │   ├── instantly.py            # fetch_campaigns
│   │   ├── report.py               # generate_report
│   │   └── s3.py                   # upload_to_s3
│   ├── models/
│   │   ├── __init__.py
│   │   └── campaign.py             # CampaignData, ReportOutput
│   ├── config.py                   # Env settings (pydantic-settings)
│   └── temporal_client.py          # Shared Temporal client factory
├── worker.py                       # Worker entry point + schedule mgmt
├── tests/
│   ├── __init__.py
│   ├── activities/
│   │   ├── test_instantly.py
│   │   ├── test_report.py
│   │   └── test_s3.py
│   ├── workflows/
│   │   └── test_campaign_sync.py
│   ├── api/
│   │   └── test_routes.py
│   └── models/
│       └── test_campaign.py
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

**Responsibilities:**
- `src/api/` — HTTP trigger surface; no business logic, only starts workflows
- `src/workflows/` — Pure control flow, deterministic, no I/O
- `src/activities/` — Side-effectful work (HTTP, S3); each isolated, retry-safe
- `src/models/` — Pydantic models shared between API and workflows
- `src/config.py` — Centralized env var access via `pydantic-settings`
- `src/temporal_client.py` — Shared `Client.connect(...)` helper so API and worker share one way of connecting
- `worker.py` — Registers workflow + activities, creates/updates schedule on startup
- `tests/` mirrors `src/` layout

**Import convention:** `src` is a package. Imports use the `src.` prefix (e.g., `from src.models.campaign import CampaignData`). This matches the spec's directory layout literally.

---

## Task 1: Project Scaffolding

Set up repo structure, dependencies, and basic tooling. No tests yet — this task is pure bootstrap so that every following task can use TDD.

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/__init__.py` (empty)
- Create: `src/api/__init__.py` (empty)
- Create: `src/api/routes/__init__.py` (empty)
- Create: `src/workflows/__init__.py` (empty)
- Create: `src/activities/__init__.py` (empty)
- Create: `src/models/__init__.py` (empty)
- Create: `tests/__init__.py` (empty) and matching subpackage `__init__.py` files
- Create: `src/config.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "instantly-to-s3"
version = "0.1.0"
description = "Weekly sync of Instantly campaign analytics to S3 as markdown reports."
requires-python = ">=3.11"
dependencies = [
    "temporalio>=1.7.0",
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "boto3>=1.34.0",
    "httpx>=0.27.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.12.0",
    "respx>=0.21.0",
    "moto[s3]>=5.0.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
.env
*.egg-info/
dist/
build/
.DS_Store
```

- [ ] **Step 3: Write `.env.example`**

```
# Instantly API
INSTANTLY_API_KEY=

# AWS / S3
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-southeast-2
S3_BUCKET_NAME=expressnext-workspace

# Temporal
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=instantly-to-s3
```

- [ ] **Step 4: Write `src/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    instantly_api_key: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "ap-southeast-2"
    s3_bucket_name: str = "expressnext-workspace"
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "instantly-to-s3"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Create empty `__init__.py` files for all packages**

```bash
touch src/__init__.py \
      src/api/__init__.py \
      src/api/routes/__init__.py \
      src/workflows/__init__.py \
      src/activities/__init__.py \
      src/models/__init__.py \
      tests/__init__.py \
      tests/activities/__init__.py \
      tests/workflows/__init__.py \
      tests/api/__init__.py \
      tests/models/__init__.py
```

- [ ] **Step 6: Install dependencies and verify**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest --collect-only
```

Expected: pytest collects 0 items with no errors.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .env.example src/ tests/
git commit -m "chore: scaffold project structure and dependencies"
```

---

## Task 2: Pydantic Models (CampaignData, ReportOutput)

TDD the data contracts before any activity logic. Use skill @test-driven-development.

**Files:**
- Create: `tests/models/test_campaign.py`
- Create: `src/models/campaign.py`

- [ ] **Step 1: Write the failing tests**

File: `tests/models/test_campaign.py`

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/models/test_campaign.py -v
```

Expected: `ImportError` on `src.models.campaign`.

- [ ] **Step 3: Implement models**

File: `src/models/campaign.py`

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/models/test_campaign.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/models/campaign.py tests/models/test_campaign.py
git commit -m "feat: add CampaignData and ReportOutput pydantic models"
```

---

## Task 3: `generate_report` Activity

Pure data transformation — start here because no external dependencies or mocking is needed. Use skill @test-driven-development.

**Files:**
- Create: `tests/activities/test_report.py`
- Create: `src/activities/report.py`

**Note on markdown content:** The spec says this is a direct port of the existing n8n Code node. The template below covers all sections listed in the spec (Campaign overview, Outreach summary table, Engagement metrics table, Email activity stats, Opportunity tracking, KPI health score, Recommendations). If the user has the original n8n JavaScript, compare the rendered output and adjust — but the tests below lock in the structural contract.

- [ ] **Step 1: Write the failing tests**

File: `tests/activities/test_report.py`

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/activities/test_report.py -v
```

Expected: `ImportError` on `src.activities.report`.

- [ ] **Step 3: Implement `generate_report`**

File: `src/activities/report.py`

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/activities/test_report.py -v
```

Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/activities/report.py tests/activities/test_report.py
git commit -m "feat: add generate_report activity with markdown template and metrics"
```

---

## Task 4: `fetch_campaigns` Activity

Fetches Instantly API and returns `list[CampaignData]`. Uses `httpx` + `respx` for mocking.

**Files:**
- Create: `tests/activities/test_instantly.py`
- Create: `src/activities/instantly.py`

- [ ] **Step 1: Write the failing tests**

File: `tests/activities/test_instantly.py`

```python
import httpx
import pytest
import respx

from src.activities.instantly import fetch_campaigns


INSTANTLY_URL = "https://api.instantly.ai/api/v2/campaigns/analytics"


def sample_api_payload() -> dict:
    return {
        "body": [
            {
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
                "total_opportunity_value": 12500.5,
            }
        ]
    }


@respx.mock
async def test_fetch_campaigns_returns_campaign_list(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    route = respx.get(INSTANTLY_URL).mock(
        return_value=httpx.Response(200, json=sample_api_payload())
    )

    campaigns = await fetch_campaigns()

    assert route.called
    assert route.calls.last.request.headers["authorization"] == "Bearer test-key"
    assert len(campaigns) == 1
    assert campaigns[0].campaign_id == "camp_123"
    assert campaigns[0].campaign_name == "Spring Outreach"


@respx.mock
async def test_fetch_campaigns_empty_body(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    respx.get(INSTANTLY_URL).mock(return_value=httpx.Response(200, json={"body": []}))
    campaigns = await fetch_campaigns()
    assert campaigns == []


@respx.mock
async def test_fetch_campaigns_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")
    respx.get(INSTANTLY_URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_campaigns()


@respx.mock
async def test_fetch_campaigns_passes_bearer_auth(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "my-secret")
    route = respx.get(INSTANTLY_URL).mock(
        return_value=httpx.Response(200, json={"body": []})
    )
    await fetch_campaigns()
    assert route.calls.last.request.headers["authorization"] == "Bearer my-secret"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/activities/test_instantly.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `fetch_campaigns`**

File: `src/activities/instantly.py`

```python
import httpx
from temporalio import activity

from src.config import get_settings
from src.models.campaign import CampaignData


INSTANTLY_ANALYTICS_URL = "https://api.instantly.ai/api/v2/campaigns/analytics"


@activity.defn
async def fetch_campaigns() -> list[CampaignData]:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.instantly_api_key}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(INSTANTLY_ANALYTICS_URL, headers=headers)
        response.raise_for_status()

    payload = response.json()
    raw_list = payload.get("body", [])
    return [CampaignData(**raw) for raw in raw_list]
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/activities/test_instantly.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/activities/instantly.py tests/activities/test_instantly.py
git commit -m "feat: add fetch_campaigns activity hitting Instantly analytics API"
```

---

## Task 5: `upload_to_s3` Activity

Uploads a markdown string to S3 at a given key. Mocked via `moto`.

**Files:**
- Create: `tests/activities/test_s3.py`
- Create: `src/activities/s3.py`

- [ ] **Step 1: Write the failing tests**

File: `tests/activities/test_s3.py`

```python
import boto3
import pytest
from moto import mock_aws

from src.activities.s3 import upload_to_s3


BUCKET = "expressnext-workspace"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("S3_BUCKET_NAME", BUCKET)
    monkeypatch.setenv("INSTANTLY_API_KEY", "unused-for-these-tests")


@mock_aws
async def test_upload_to_s3_puts_object(aws_env):
    s3 = boto3.client("s3", region_name="ap-southeast-2")
    s3.create_bucket(
        Bucket=BUCKET,
        CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
    )

    await upload_to_s3("# hello", "campaigns/instantly-campaigns/test 2026-04-20.md")

    obj = s3.get_object(
        Bucket=BUCKET, Key="campaigns/instantly-campaigns/test 2026-04-20.md"
    )
    assert obj["Body"].read().decode("utf-8") == "# hello"
    assert obj["ContentType"] == "text/markdown"


@mock_aws
async def test_upload_to_s3_overwrites_existing_object(aws_env):
    s3 = boto3.client("s3", region_name="ap-southeast-2")
    s3.create_bucket(
        Bucket=BUCKET,
        CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
    )
    key = "campaigns/instantly-campaigns/overwrite 2026-04-20.md"

    await upload_to_s3("first", key)
    await upload_to_s3("second", key)

    obj = s3.get_object(Bucket=BUCKET, Key=key)
    assert obj["Body"].read().decode("utf-8") == "second"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/activities/test_s3.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `upload_to_s3`**

File: `src/activities/s3.py`

```python
import asyncio

import boto3
from temporalio import activity

from src.config import get_settings


def _put_object(content: str, key: str) -> None:
    settings = get_settings()
    client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/markdown",
    )


@activity.defn
async def upload_to_s3(content: str, key: str) -> None:
    await asyncio.to_thread(_put_object, content, key)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/activities/test_s3.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/activities/s3.py tests/activities/test_s3.py
git commit -m "feat: add upload_to_s3 activity writing markdown to configured bucket"
```

---

## Task 6: `InstantlyToS3Workflow` Definition

Orchestrates the three activities. Per-campaign iterations are independent: one failure is logged and the workflow continues.

**Files:**
- Create: `tests/workflows/test_campaign_sync.py`
- Create: `src/workflows/campaign_sync.py`

**Determinism rules:** Inside the workflow, use `workflow.now()` (not `datetime.now()`), `workflow.logger`, and call activities only through `workflow.execute_activity`.

- [ ] **Step 1: Write the failing tests**

File: `tests/workflows/test_campaign_sync.py`

```python
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
        ):
            await env.client.execute_workflow(
                InstantlyToS3Workflow.run,
                id="wf-3",
                task_queue="test-q",
            )

    uploaded_names = {k.split("/")[-1].split(" ")[0] for k, _ in fake_state.uploads}
    assert "Beta" in uploaded_names
    assert "Alpha" not in uploaded_names
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/workflows/test_campaign_sync.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement workflow**

File: `src/workflows/campaign_sync.py`

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/workflows/test_campaign_sync.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/workflows/campaign_sync.py tests/workflows/test_campaign_sync.py
git commit -m "feat: add InstantlyToS3Workflow orchestrating fetch/report/upload"
```

---

## Task 7: Temporal Client Helper + Worker Entry Point + Schedule Management

Creates `worker.py` that registers the workflow/activities and idempotently creates (or updates) the weekly schedule on startup.

**Files:**
- Create: `src/temporal_client.py`
- Create: `worker.py`
- Create: `tests/test_schedule.py`

- [ ] **Step 1: Write `src/temporal_client.py`**

```python
from temporalio.client import Client

from src.config import get_settings


async def connect() -> Client:
    settings = get_settings()
    return await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
```

- [ ] **Step 2: Write a small test for the schedule spec builder**

File: `tests/test_schedule.py`

```python
from worker import build_schedule_spec


def test_schedule_uses_weekly_monday_midnight_utc_cron():
    spec = build_schedule_spec()
    assert spec.cron_expressions == ["0 0 * * 1"]
```

- [ ] **Step 3: Run test — expect failure**

```bash
pytest tests/test_schedule.py -v
```

Expected: `ImportError` on `worker`.

- [ ] **Step 4: Implement `worker.py`**

**Note on the schedule update path:** The exact shape of `handle.update(...)` varies slightly across `temporalio` versions. If the snippet below doesn't type-check against your installed `temporalio>=1.7.0`, check `help(handle.update)` — the supported pattern is to return a `ScheduleUpdate(schedule=...)` from the callback. The import names (`ScheduleAlreadyRunningError` vs. catching `temporalio.service.RPCError` with `ALREADY_EXISTS`) may also need a small adjustment to match the installed SDK. The behavior the plan locks in: create on first run, update the spec/action on every subsequent startup.


File: `worker.py`

```python
import asyncio
import logging

from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleSpec,
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
        await handle.update(lambda _input: _input.schedule.__class__(
            action=schedule.action,
            spec=schedule.spec,
        ))
        logger.info("updated existing schedule %s", SCHEDULE_ID)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    client = await connect()

    await ensure_schedule(client)

    async with Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[InstantlyToS3Workflow],
        activities=[fetch_campaigns, generate_report, upload_to_s3],
    ):
        logger.info("worker listening on task_queue=%s", settings.temporal_task_queue)
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Run test — expect pass**

```bash
pytest tests/test_schedule.py -v
```

Expected: 1 test passes.

- [ ] **Step 6: Commit**

```bash
git add src/temporal_client.py worker.py tests/test_schedule.py
git commit -m "feat: add Temporal worker entry point with idempotent weekly schedule"
```

---

## Task 8: FastAPI App (`/health` and `/trigger`)

Thin API surface: `/health` returns 200; `/trigger` starts the workflow.

**Files:**
- Create: `tests/api/test_routes.py`
- Create: `src/api/main.py`
- Create: `src/api/routes/workflows.py`

- [ ] **Step 1: Write the failing tests**

File: `tests/api/test_routes.py`

```python
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.main import app, get_temporal_client


def test_health_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trigger_starts_workflow():
    fake_handle = MagicMock()
    fake_handle.id = "instantly-to-s3-manual-abc"
    fake_client = MagicMock()
    fake_client.start_workflow = AsyncMock(return_value=fake_handle)

    app.dependency_overrides[get_temporal_client] = lambda: fake_client
    try:
        with TestClient(app) as client:
            response = client.post("/trigger")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["workflow_id"] == "instantly-to-s3-manual-abc"
    fake_client.start_workflow.assert_awaited_once()
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/api/test_routes.py -v
```

Expected: `ImportError` on `src.api.main`.

- [ ] **Step 3: Implement the route module**

The route takes the Temporal-client dependency as an argument so the app factory in `main.py` wires it in. This keeps the route module free of any reference back to `main.py` (no circular import) while still letting tests override the dependency via `app.dependency_overrides`.

File: `src/api/routes/workflows.py`

```python
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
```

- [ ] **Step 4: Implement the FastAPI app**

File: `src/api/main.py`

```python
from fastapi import FastAPI

from src.api.routes.workflows import build_router
from src.temporal_client import connect


async def get_temporal_client():
    return await connect()


app = FastAPI(title="instantly-to-s3")
app.include_router(build_router(get_temporal_client))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/api/test_routes.py -v
```

Expected: 2 tests pass.

- [ ] **Step 6: Run the full test suite**

```bash
pytest -v
```

Expected: all previous tests still pass (models, activities, workflow, schedule, API).

- [ ] **Step 7: Commit**

```bash
git add src/api/ tests/api/
git commit -m "feat: add FastAPI app with /health and /trigger endpoints"
```

---

## Task 9: Docker + docker-compose for Local Dev

Run Temporal server + UI, FastAPI, and the worker together.

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

COPY src/ src/
COPY worker.py ./

EXPOSE 8000

# Default command runs the API; the worker service overrides this in compose.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  temporal:
    image: temporalio/auto-setup:1.24
    environment:
      - DB=sqlite
      - SKIP_SCHEMA_SETUP=false
    ports:
      - "7233:7233"

  temporal-ui:
    image: temporalio/ui:2.27.0
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - TEMPORAL_CORS_ORIGINS=http://localhost:3000
    ports:
      - "8080:8080"
    depends_on:
      - temporal

  api:
    build: .
    env_file: .env
    environment:
      - TEMPORAL_HOST=temporal:7233
    ports:
      - "8000:8000"
    depends_on:
      - temporal

  worker:
    build: .
    env_file: .env
    environment:
      - TEMPORAL_HOST=temporal:7233
    command: ["python", "worker.py"]
    depends_on:
      - temporal
```

- [ ] **Step 3: Build and launch the stack**

```bash
cp .env.example .env
# fill in INSTANTLY_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
docker compose up --build -d
```

Expected: all four services come up. `docker compose ps` shows them `running`.

- [ ] **Step 4: Verify `/health`**

```bash
curl -sf http://localhost:8000/health
```

Expected: `{"status":"ok"}`.

- [ ] **Step 5: Verify worker registered the schedule**

Open http://localhost:8080 → Schedules tab → confirm `instantly-to-s3-weekly` exists with cron `0 0 * * 1`.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "chore: add Dockerfile and docker-compose for local dev"
```

---

## Task 10: Manual Trigger Smoke Test + README

End-to-end verification against the real Instantly API and a real S3 bucket (or a test bucket), plus a README so future engineers can run it.

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
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

- API:       http://localhost:8000
- Temporal UI: http://localhost:8080

## Manual trigger

```bash
curl -X POST http://localhost:8000/trigger
```

Returns `{"workflow_id": "instantly-to-s3-manual-XXXXXXXX"}`. Tail the run in the Temporal UI.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Configuration

See `.env.example` for all variables. Defaults:
- `AWS_REGION=ap-southeast-2`
- `S3_BUCKET_NAME=expressnext-workspace`
- `TEMPORAL_HOST=localhost:7233`
- `TEMPORAL_TASK_QUEUE=instantly-to-s3`
````

- [ ] **Step 2: Smoke test — manual trigger end-to-end**

With `docker compose up` running and a real `.env`:

```bash
curl -X POST http://localhost:8000/trigger
```

- [ ] **Step 3: Verify run in Temporal UI**

Open http://localhost:8080 → Workflows → find the `instantly-to-s3-manual-XXXXXXXX` run → confirm it completed successfully.

- [ ] **Step 4: Verify S3 objects**

```bash
aws s3 ls s3://expressnext-workspace/campaigns/instantly-campaigns/ --region ap-southeast-2
```

Expected: one `.md` per campaign, named `{campaign_name} {YYYY-MM-DD}.md`. Download one and eyeball the markdown.

- [ ] **Step 5: Verify idempotent re-trigger**

Trigger again:

```bash
curl -X POST http://localhost:8000/trigger
```

Confirm the same S3 keys are overwritten (check the `LastModified` timestamps).

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: add README with local dev, trigger, and smoke test instructions"
```

---

## Verification Checklist

Before calling this plan done, confirm:

- [ ] `pytest` passes with 0 failures
- [ ] `docker compose up --build` brings up all four services
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] `POST /trigger` starts a workflow visible in the Temporal UI
- [ ] The scheduled workflow `instantly-to-s3-weekly` exists with cron `0 0 * * 1`
- [ ] At least one `.md` file appears under `s3://expressnext-workspace/campaigns/instantly-campaigns/` after a successful run
- [ ] Re-triggering on the same day overwrites the same keys (no date suffix collisions, no duplicate files)
