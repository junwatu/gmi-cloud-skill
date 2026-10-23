# Media jobs

Use `python3 <skill-dir>/scripts/gmi_api.py` below as `HELPER`.

## Discover and build a payload

```sh
HELPER models --kind media --search "Seedance 2.5" --details
HELPER model EXACT_MODEL_ID
```

Read [catalog discovery](catalog.md). Both `models` and `catalog` combine public
model documentation with live API listings. Exact IDs and aliases are dynamic;
no model family is excluded by a hard-coded list. Documentation-only offerings
remain visible, with links to resolve their IDs and endpoint requirements.

`media-models` is the raw media-ID endpoint. Detailed responses can include
`parameters`, modalities, `model_type`, `status`, `qworkers`, `model_metadata`, and
`price_info`. Worker/status metadata is reported separately from model discovery.
The helper does not block an authorized submission because of `qworkers == 0`
or a status snapshot; the official submit API decides acceptance. With zero
workers, queue duration is unknown. Do not promise immediate generation.

Write `payload.json` from the chosen model's schema. Names differ by model:
`prompt`, `text`, `lyrics`, `duration`, `durationSeconds`, etc. The helper checks
known fields, required values/defaults, primitive types and enum choices.
GMI validates model-specific nested structures. Prefer URLs for media inputs;
local uploads require the documented upload workflow and authorization to make
the input publicly accessible. The helper does not implement uploads.

`price_info.price` was observed in the inspected community repo as millionths
of USD per `unit`. The helper preserves raw metadata instead of assuming a
universal conversion or comparing incomparable units. Do not invent totals.

## Approval before submission

Follow [Approval before spending](../SKILL.md#approval-before-spending) before
`submit`. Prepare the exact model and payload, number of jobs and outputs, USD
estimate and calculation from current price units/quantities. Do not assume one
request always produces one output. Disclose unknown pricing or variable charges
and wait for explicit approval. Include the monitoring window, variable interval
and any known or unknown host usage cost in that approval. A generation request
only authorizes preparation.
Any change increasing the approved cost requires new approval. Submit only the
approved work, once; uncertainty after submission is handled by reconciliation.

The helper's manual `submit` command does not prompt for approval. Agents must
complete the approval workflow before invoking it.

## Submit once, resume by ID

```sh
HELPER submit --model MODEL_ID --payload-file payload.json --job-id scene-01
HELPER status scene-01
HELPER follow-up scene-01 --out ./outputs/scene-01
HELPER download scene-01 --out ./outputs/scene-01
HELPER jobs
HELPER requests --limit 20
```

`submit` returns after the HTTP submission response. GMI continues processing
without a local process. Choose a unique local `--job-id` or omit it for a UUID.
Reusing a local ID refuses a second submission. Another ID can submit another
billed job; there is no global deduplication.

By default, return to the user after acceptance and use the native host scheduler
with the offline `follow-up` plan for variable 2–5 minute checks. See
[scheduled follow-up](follow-up.md). Do not chain a blocking wait. The helper
returns a plan; the host must confirm the actual schedule. If scheduling is
unavailable, report that and leave a manual resume command.

A private intent record is created before POST. The accepted request ID is saved
before reporting status. Immediate synchronous success/failure uses the same
terminal handling as polled results. Paid POSTs are never retried. Official docs
describe async video; the community implementation also observed sync media.

`status` does one lookup. `wait` uses 1-to-10-second backoff, jitter, a polling
time budget, and at most three consecutive transient read errors. Each HTTP call
also has a socket timeout bounded by the remaining budget; a slow streaming
response can exceed that budget, so this is not a hard process deadline. HTTP 429 respects
Retry-After within that budget; daily quotas stop without retry. GET 408/429/
500/502/503/504 and connection failures can be retried. Authentication, 404,
malformed responses and unknown statuses stop. The helper has no daemon or remote
cancellation. `wait` remains an explicit opt-in; native scheduled checks use a
single `status` call per wake, then recalculate and update the same monitor.

| Exit | Meaning | Action |
|---|---|---|
| 0 | Command succeeded or job completed successfully | Inspect returned status/artifacts |
| 1 | API, terminal failure, unknown status, state or download error | Explain the error; keep the ID |
| 2 | Invalid arguments or payload | Correct local input |
| 3 | Job pending or wait elapsed | Resume the same ID |
| 130 | Local wait interrupted | Remote job may continue |

Pending: `created`, `queued`, `pending`, `dispatched`, `processing`, `running`, `in_progress`.
Success: `success`, `completed`, `succeeded`.
Failure: `failed`, `error`, `cancelled`, `canceled`, `expired`, `rejected`.
Unknown states are preserved and return an error, avoiding indefinite polling.

## Uncertain acceptance

If POST times out, returns an error, lacks an ID, or the process exits between
acceptance and saving, do not submit again automatically. The intent stays
`submission_unknown` or `submitting`. Reconcile with recent server requests:

```sh
HELPER requests --limit 20
# Identify the exact request using model/time/payload in GMI first:
HELPER attach scene-01 --request-id VERIFIED_REQUEST_ID
HELPER wait scene-01 --timeout 45
```

Never attach a request merely because its model matches. `attach` fetches the
request, checks its model, and refuses to replace a different ID. Absence from a
recent page does not prove rejection. Any ID hint from a submission error is
stored for review, not treated as a successful acceptance.

## Downloads and privacy

Download requires success. Known artifact URL fields are deduplicated; thumbnails
are fallback only. Artifact GETs use a separate opener without API auth. Only
HTTPS URLs and HTTPS redirects are accepted; embedded credentials are refused.
Downloads stream to temporary files, then deterministic filenames. The default
per-file limit is 1 GiB (`--max-bytes` changes it). Completed files get SHA-256
records; repeats reuse them only when their hash matches. Partial failures retain
completed files and return nonzero. Refresh job status if signed links expire;
never regenerate just to refresh a link.

On POSIX, registry files are mode 600 and new state directories mode 700. Windows
uses inherited user-directory ACLs; the helper does not set Windows ACLs. No raw submitted
prompts/payloads are persisted. Result metadata and signed URLs are private.
State belongs to its machine/directory and original GMI account/organization;
resume using the corresponding credentials.

Sources reviewed 2026-10-23:
- [GMI media/video API](https://docs.gmicloud.ai/inference-engine/api-reference/video-api-reference): queue, schemas, polling, artifacts.
- [GMI rate limits](https://docs.gmicloud.ai/inference-engine/api-reference/rate-limit).
- [GMI video SDK reference](https://docs.gmicloud.ai/inference-engine/api-reference/video-sdk-reference): the documented `created` request state is treated as pending. Worker metadata observed from the API is not an official admission rule.

Catalog listing and selected readiness metadata were verified live. Job lifecycle
and downloads were validated with local HTTP fixtures; paid generation remains
unverified.

Run the bundled regression suite with:
`python3 -m unittest discover -s <skill-dir>/scripts -p 'test_*.py'`.
