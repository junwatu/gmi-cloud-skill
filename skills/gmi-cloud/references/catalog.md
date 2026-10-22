# Discover models without hiding offerings

Use `python3 <skill-dir>/scripts/gmi_api.py` below as `HELPER`.

```sh
HELPER models --out ./gmi-models.json
HELPER models --search "Seedance 2.5" --details
HELPER models --kind media --search "WAN 3.0" --details
HELPER models --kind text
HELPER models --api-only
```

`catalog` is an alias for `models`. Both use the same combined default.
`text-models` returns the raw inference catalog; `media-models` returns raw media
IDs. `model EXACT_ID` fetches media parameters. Breaking change from beta.5:
`models` no longer returns the raw text-only `{data: [...]}` response. Scripts
needing the old shape must use `text-models`.

## Three live sources

1. [Official documentation index](https://docs.gmicloud.ai/llms.txt): named model
   quickstarts across text, image, video and audio. Public, no API key required.
   The parser follows entries under `/model-quickstarts/`, excluding category
   overview pages. This is discovery metadata, not an execution allowlist.
2. [Inference model list](https://docs.gmicloud.ai/inference-engine/api-reference/llm-api-reference):
   `GET https://api.gmi-serving.com/v1/models`, using the current key/organization.
3. [Media model list and details](https://docs.gmicloud.ai/inference-engine/api-reference/video-api-reference):
   `GET https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/models` returns
   `model_ids`; `GET .../models/{id}` provides parameters and metadata.

Each invocation refreshes these sources. There is no stored catalog or fixed
model list, version cutoff, default top-N cap, or blacklist. A published model
missing from an account catalog remains visible from official documentation.
An API model missing from docs remains visible from its API listing. API-only
entries may include test/internal records; distinguish them from documented
products rather than silently excluding entries from an all-model request.

Aliases come from current documentation names and slugs. They merge into API
records only when a normalized exact ID comparison gives one unambiguous match
in the appropriate source. No guessed API ID is assigned to documentation-only
records. Conflicting/ambiguous identities remain separate records to preserve
coverage. Search ignores punctuation, case and spacing and runs after alias merge.
This is spelling normalization, not semantic/fuzzy or release-order matching.
If a full name misses, search its family and follow the official page.

## Result fields

| Field | Meaning |
|---|---|
| `source_counts` | Raw records returned by each source before search/merge |
| `matched` | Result records after merge and requested search/scope |
| `complete` | All requested sources/details completed without errors |
| `successful_sources`, `errors` | Precisely which lookups succeeded or failed |
| `warnings` | Nonfatal anomalies, such as an upstream empty model ID |
| `models[].id` | Exact API-listed ID, or `null` for unresolved documentation entries |
| `documented`, `documentation` | Public quickstart evidence and URLs |
| `api_listing` | `listed`, `not_returned`, or `unknown` |
| `readiness` | Worker/status telemetry when inspected, otherwise `unknown` |

`not_returned` means the relevant account endpoint completed but did not contain
an unambiguously matching ID. It does not establish lack of access or product
removal. `unknown` covers unqueried/failed API coverage. Documentation URLs/titles
are not credentials; public requests never receive API authorization headers.

`--details` fetches metadata for matching media API entries, including `status`,
`qworkers`, modalities and raw price data. Narrow the search before using it to
avoid hundreds of extra lookups. Counts are a snapshot, not an admission test.
`workers_reported`, `no_workers_reported` and `inactive_reported` describe the
response; the helper does not use them as local submission gates. The official
media API contract does not document a `qworkers > 0` submission prerequisite.

## Full output and degraded discovery

`--out PATH` writes the complete JSON atomically and prints a short summary with
its path. It does not truncate records. Files can be searched or shared without
pasting hundreds of entries into chat. Result limits imposed by an agent's tool
viewer must not become a silent limit in the user's catalog.

Without `GMI_API_KEY`, official documentation is still returned; missing account
coverage is explicit and the command exits 1. TLS, authentication or docs-index
failures likewise retain successful sources and return `complete: false`, exit 1.
A malformed empty index is an error, not a successful zero-model response.

The official list contracts consulted are unpaginated. If an endpoint starts
signaling more pages, the helper preserves the received entries and reports
`CATALOG_INCOMPLETE` rather than claiming a full result. A changed index/API schema
also needs an implementation update; it is never proof GMI has no models.

## Coverage boundaries

Discovery covers the official public model quickstart index and the two account
API endpoints. It cannot promise that every private, regional, newly announced,
console-only or separately deployed model is exposed through those sources.
GMI documents [dedicated deployments](https://docs.gmicloud.ai/inference-engine/marketplace/dedicated)
as a separate workflow. When a user supplies an official model URL absent from
discovery, read it and report the documented offering and endpoint requirements;
do not call it unsupported or invent an ID or permission grant.

Official docs were reviewed 2026-10-23, including the
[Seedance 2.5 quickstart](https://docs.gmicloud.ai/model-quickstarts/video/seedance-2-5-260628).
Release recency requires current official release evidence, not catalog order.

Official starting point: [GMI Model Library](https://docs.gmicloud.ai/model-quickstarts/model-library).
If a named offering is missing from the index/API union, consult the current
library and official GMI documentation search before making an absence claim.
