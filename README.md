# GMI Cloud Skill — Public Beta

![Public beta](https://img.shields.io/badge/status-public%20beta-orange)

A Codex skill for GMI Cloud model discovery from official documentation and live
account catalogs, text inference, and resumable image, video, and audio generation. Written in Python using only the standard library.

**Version: `v0.1.0-beta.6`.** Expect changes while API behavior and platform support
are validated. This is an independent community project, not an official GMI Cloud product.

## Install

Ask Codex:

```text
Use $skill-installer to install gmi-cloud from
https://github.com/junwatu/gmi-cloud-skill/tree/v0.1.0-beta.6/skills/gmi-cloud
```

Or download `gmi-cloud.zip` from the
[beta release](https://github.com/junwatu/gmi-cloud-skill/releases/tag/v0.1.0-beta.6)
and follow the [manual installation guide](skills/gmi-cloud/README.md#install-in-codex).

## Requirements

- Python 3.10+ with standard-library TLS support; no pip dependencies.
- Codex with local skill support and permission to execute Python.
- `GMI_API_KEY` for account listings and generation; optional `GMI_ORG_ID`.
  Public model documentation can be discovered without a key.
- Network access to `docs.gmicloud.ai`, GMI API endpoints and artifact hosts, writable local storage,
  and GMI model access/credits for paid requests.

See the [complete setup and usage guide](skills/gmi-cloud/README.md).

## All-model discovery by default

`models` and `catalog` now query three live sources: GMI's official public model
quickstart index, the inference model API, and the media model API. There is no
cached model list, version cutoff or default top-N limit. Documented models remain
visible even if the current API key cannot list them. API-only entries remain
visible too. Source failures are explicit and successful results are retained.

```sh
python3 skills/gmi-cloud/scripts/gmi_api.py models --out ./gmi-models.json
python3 skills/gmi-cloud/scripts/gmi_api.py models --search "WAN 3.0" --details
python3 skills/gmi-cloud/scripts/gmi_api.py models --search "Seedance 2.5" --details
```

On Windows use `py -3`. The full JSON export includes every result, source counts,
documentation URLs and lookup errors/warnings. Search matches current IDs and
public documentation aliases. No credentials are included in the export.

**Compatibility change:** `models` returns the combined catalog in beta.6.
Use `text-models` for the previous raw inference `{data: [...]}` response.
`media-models` remains the raw media-ID endpoint.

Worker count and status snapshots do not hide models or block an authorized
submission. GMI's submit API decides acceptance. The docs do not define
`qworkers > 0` as a prerequisite. A public quickstart establishes a documented
offering, not a grant of generation access to every account.

Read the [catalog guide](skills/gmi-cloud/references/catalog.md) for source scope,
public discovery without a key, aliases, partial results and dedicated endpoints.

## Async media jobs

Submit once, save the request ID, and resume status polling later. The helper
handles immediate and asynchronous failures, bounded waiting, rate limits,
uncertain submission acceptance, and artifact downloads with integrity checks.
It does not automatically retry paid submissions. Stopping local waiting does
not cancel remote work; there is no background monitoring daemon.

## Beta verification

64 offline tests pass locally on macOS with Python 3.13. Windows/Linux path logic
has simulated coverage; native Windows/Linux testing remains unverified.
Tests are run manually. This repository has no automatic GitHub Actions workflow.
Read-only discovery was verified against the official documentation index and
both account APIs with a trusted CA bundle. Coverage checks preserve every
nonempty API ID and every indexed model quickstart URL in the merged output.
Live generation, provisioning, and media uploads remain unverified.
The helper implements inference and media, with compute guidance as reference only.

From the repository root:

```sh
python3 -m unittest discover -s skills/gmi-cloud/scripts -p 'test_*.py'
```

On Windows, use `py -3` in place of `python3`.

Report issues with OS, Python version, command, and sanitized error output.
Never include API keys, private prompts, signed artifact URLs, or job-state files.
