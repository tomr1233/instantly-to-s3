# Leads to S3 — Per-Campaign Lead Export

## Purpose

Extend `InstantlyToS3Workflow` so that, in addition to generating a markdown analytics report per campaign, it also exports the full list of leads for each campaign to S3 as JSON. Runs on the same weekly schedule, in the same per-campaign loop, using the existing failure-isolation pattern.

Downstream consumers (Athena, ad-hoc analysis) get a weekly lossless snapshot of lead state per campaign alongside the existing analytics reports.

## Scope

- One new activity: `fetch_leads` in `src/activities/instantly.py`.
- One generalized activity: `upload_to_s3` gains an optional `content_type` argument.
- One new branch inside the existing per-campaign loop in `InstantlyToS3Workflow.run`.
- One new worker registration entry.
- Test coverage for the new activity, the generalized upload, and the workflow branch.

No new workflow, no new schedule, no new model, no new configuration.

## Architecture

```
Temporal Schedule (weekly cron) — unchanged
  -> InstantlyToS3Workflow
    -> Activity: fetch_campaigns                    (unchanged)
    -> For each campaign:
        -> Activity: generate_report                (unchanged)
        -> Activity: upload_to_s3 (markdown)        (unchanged, now uses default content_type)
        -> If campaign.leads_count > 0:             (NEW)
            -> Activity: fetch_leads                (NEW — paginates Instantly API)
            -> Activity: upload_to_s3 (JSON)        (same activity, content_type="application/json")
```

Failure isolation stays at the per-campaign boundary. The existing `try/except Exception` in the loop now covers both the report branch and the leads branch.

## Workflow Changes — `InstantlyToS3Workflow`

Inside the existing per-campaign loop in `src/workflows/campaign_sync.py`, after the current `upload_to_s3` call for the markdown report:

1. If `campaign.leads_count == 0`, log at DEBUG and skip — no `fetch_leads` call, no upload.
2. Otherwise:
   a. Execute `fetch_leads(campaign.campaign_id)` — returns a JSON-encoded string of the full leads list (serialization happens inside the activity, see "Serialization boundary" below).
   b. Build the S3 key: `campaigns/instantly-leads/{campaign_name} {YYYY-MM-DD}.json`, using the same `run_date` already computed at the top of `run` via `workflow.now()`.
   c. Execute `upload_to_s3(leads_json, key, content_type="application/json")`.
   d. Log at INFO with `campaign_id`, `lead_count` (derivable from the activity result or a separate return — see Activities section), and `key`.

Re-runs on the same day overwrite the same S3 keys — acceptable and consistent with how the existing report upload behaves.

### Serialization boundary

`fetch_leads` returns a `str` (already `json.dumps`'d) rather than `list[dict]`. Rationale:

- 1–2k leads per campaign can produce a few MB of JSON. Temporal's default payload limit between workflow and activity is ~2MB.
- Keeping the raw list inside the activity means the large payload crosses the workflow/activity boundary exactly once (on the way to `upload_to_s3`), instead of twice (activity → workflow → activity).
- `json.dumps` is not meaningfully needed inside the workflow for any reason — the workflow doesn't inspect individual leads.

To preserve a lead count for logging, the activity can additionally return the count, but the simplest design is to return a small wrapper:

- Option 1: return `str`, derive count by `json.loads(...)` in the workflow — wasteful.
- Option 2: return a tuple `(str, int)` — fine but awkward to type.
- Option 3 (chosen): return a pydantic model `LeadsPayload(leads_json: str, lead_count: int)`.

See the Models section.

## Activities

### `fetch_leads`

- **Location:** `src/activities/instantly.py`
- **Input:** `campaign_id: str`
- **Output:** `LeadsPayload` (see Models)
- **Side effects:** HTTP POST(s) to `https://api.instantly.ai/api/v2/leads/list`
- **Retry policy:** `FETCH_RETRY` (3 attempts, 2s → 30s exponential backoff) — same as `fetch_campaigns`.
- **`start_to_close_timeout`:** 5 minutes — generous headroom for ~20 paginated requests under slow network conditions.

**Pagination behavior:**

- Request body: `{"campaign": campaign_id, "limit": 100}` on the first page.
- Response shape is assumed to follow Instantly's standard cursor pattern: `{"items": [...], "next_starting_after": "<cursor-or-null>"}`. The exact field names must be verified against the live API during implementation; adjust parsing if they differ.
- While `next_starting_after` is present and non-null, send another POST with `{"campaign": campaign_id, "limit": 100, "starting_after": <cursor>}` and append `items` to the accumulator.
- Stop when the cursor is absent or null.
- Return `LeadsPayload(leads_json=json.dumps(all_items), lead_count=len(all_items))`.

**Authentication:** same bearer token pattern as `fetch_campaigns` — reads `INSTANTLY_API_KEY` via `get_settings()`.

**Error handling:** `response.raise_for_status()` after each page. A failure on page N causes the entire activity to fail, triggering Temporal's retry policy from page 1. Acceptable given the small page count.

**Rate limiting (v1):** none. If 429s become observed in practice, we can add a small inter-page sleep — not in scope now.

### `upload_to_s3` (generalized)

- **Location:** `src/activities/s3.py`
- **Signature change:** `upload_to_s3(content: str, key: str, content_type: str = "text/markdown") -> None`
- **Behavior:** identical to today for existing callers (default content type stays `"text/markdown"`), plus passes `content_type` through to `client.put_object(..., ContentType=content_type)`.
- **Retry policy:** `UPLOAD_RETRY` (3 attempts, backoff) — unchanged.

Existing report callers do not change. Leads callers pass `content_type="application/json"`.

### `fetch_campaigns`, `generate_report`

Unchanged.

## Models

### `LeadsPayload` (new)

`src/models/campaign.py`:

```python
class LeadsPayload(BaseModel):
    leads_json: str
    lead_count: int
```

No model for individual leads — leads are stored as raw JSON to stay lossless against Instantly's evolving schema, and the workflow never inspects individual records.

### `CampaignData`, `ReportOutput`

Unchanged.

## S3 Layout

| Artifact | Key pattern | Content-Type |
|---|---|---|
| Analytics report (existing) | `campaigns/instantly-campaigns/{campaign_name} {YYYY-MM-DD}.md` | `text/markdown` |
| Leads export (new) | `campaigns/instantly-leads/{campaign_name} {YYYY-MM-DD}.json` | `application/json` |

Bucket: `expressnext-workspace` (shared with reports — confirmed scoped for this data).

## Configuration

No new environment variables. All behavior uses existing settings.

## Worker Registration

`worker.py`: add `fetch_leads` to the `activities=[...]` list:

```python
activities=[fetch_campaigns, fetch_leads, generate_report, upload_to_s3],
```

## Error Handling and Observability

Three failure modes, all caught by the existing per-campaign `try/except Exception`:

1. **Leads fetch fails after retries** — logged with `campaign_id` and campaign name, loop continues. The report for the same campaign was uploaded earlier in the iteration and is preserved.
2. **Leads upload fails after retries** — logged, loop continues.
3. **Instantly API partial pagination failure** — Temporal retries the entire activity from page 1 (3 attempts total). If all attempts fail, falls through to case 1.

**Log levels:**
- `INFO` on successful leads upload: `campaign_id`, `lead_count`, `key`.
- `DEBUG` on skipped zero-lead campaigns (avoids noise).
- `EXCEPTION` on the outer `except`, unchanged.

**Re-runs:** deterministic `run_date` from `workflow.now()` means same-day re-runs overwrite the same S3 keys — matches existing report behavior.

## Testing

Mirror the existing test layout under `tests/activities/` and `tests/workflows/`. HTTP mocking uses `respx` (already used by `tests/activities/test_instantly.py`).

### `tests/activities/test_instantly_leads.py` (new file)

- **Single page, happy path:** mock responds with `{"items": [{...}, {...}], "next_starting_after": None}`. Assert `fetch_leads("camp_123")` returns a `LeadsPayload` whose `leads_json` parses back to the input list and whose `lead_count == 2`. Assert bearer header present and request body contains `campaign: "camp_123"` and `limit: 100`.
- **Multi-page pagination:** first response has cursor `"abc"`, second has `None`. Assert both pages fetched (two calls), `leads_json` contains leads from both pages in order, and the second call included `starting_after: "abc"`.
- **Empty response:** `{"items": [], "next_starting_after": None}` → returns `LeadsPayload(leads_json="[]", lead_count=0)`.
- **HTTP error:** 500 response → raises `httpx.HTTPStatusError` (exercises the path that triggers Temporal retry).

### `tests/activities/test_s3.py` (extend existing)

- **Default content type regression:** `upload_to_s3("# heading", "k.md")` called without a content type still invokes `put_object` with `ContentType="text/markdown"`.
- **JSON content type:** `upload_to_s3("[]", "k.json", "application/json")` invokes `put_object` with `ContentType="application/json"`.

Use the same S3 mocking approach already in place in `tests/activities/test_s3.py`.

### `tests/workflows/test_campaign_sync.py` (extend existing)

- **Leads branch runs when `leads_count > 0`:** with a mock campaign having `leads_count=1000`, the workflow calls `fetch_leads` once and calls `upload_to_s3` a second time with the `campaigns/instantly-leads/...json` key and `content_type="application/json"`.
- **Leads branch skipped when `leads_count == 0`:** no `fetch_leads` call, no second `upload_to_s3`.
- **Leads failure isolation:** if `fetch_leads` raises, the report upload for that campaign still succeeded (verify it was called first) and the workflow proceeds to the next campaign without raising.

## What's Not Included

- No per-lead pydantic model — leads remain raw JSON.
- No delta/incremental export — v1 dumps the full leads list per campaign each run. If payload sizes grow, revisit.
- No rate-limit-aware pagination (inter-page sleeps / 429 backoff beyond Temporal's retry policy). Revisit if 429s are observed.
- No separate leads schedule or separate workflow — same cadence and same workflow as reports.
- No encryption/ACL changes to the S3 bucket — confirmed in scope for this data already.
