# GMI Cloud Skill — Public Beta

![Public beta](https://img.shields.io/badge/status-public%20beta-orange)

An agent skill for GMI Cloud model discovery from official documentation and live
account catalogs, text inference, and resumable image, video, and audio generation. Written in Python using only the standard library.

**Version: `v0.1.0-beta.9`.** Expect changes while API behavior and platform support
are validated. This is an independent community project, not an official GMI Cloud product.

## Install

Ask Codex:

```text
Use $skill-installer to install gmi-cloud from
https://github.com/junwatu/gmi-cloud-skill/tree/v0.1.0-beta.9/skills/gmi-cloud
```

Or download `gmi-cloud.zip` from the
[beta release](https://github.com/junwatu/gmi-cloud-skill/releases/tag/v0.1.0-beta.9)
and follow the [manual installation guide](skills/gmi-cloud/README.md#install-in-codex).

## Host compatibility

The skill uses `SKILL.md` plus a Python helper. The following hosts document
support for this layout; this is **format compatibility, not a claim of tested
execution in every host**.

| Host | Global skill folder | Verification |
|---|---|---|
| Codex | `$CODEX_HOME/skills/gmi-cloud/` (default `~/.codex/skills/gmi-cloud/`) | Used locally; helper tests and read-only GMI discovery verified on macOS |
| [Claude Code](https://code.claude.com/docs/en/skills) | `~/.claude/skills/gmi-cloud/` | Documented format support; host execution untested |
| [Grok Build/CLI](https://docs.x.ai/build/features/skills-plugins-marketplaces) | `~/.grok/skills/gmi-cloud/` | Documented format support; host execution untested |
| [Antigravity CLI](https://antigravity.google/docs/skills) | `~/.gemini/antigravity-cli/skills/gmi-cloud/` | Documented format support; host execution untested |
| [OpenCode](https://opencode.ai/docs/skills) | `~/.config/opencode/skills/gmi-cloud/` | Documented format support; host execution untested |

`~` means your user home directory. Copy the **entire `gmi-cloud` folder**, including
`scripts/` and `references/`, into one location discovered by your host. Avoid
installing duplicate copies in multiple discovery paths.

Claude Code and Grok Build/CLI expose `/gmi-cloud`; Antigravity CLI also converts
skills into slash commands. In OpenCode, ask the agent to load the `gmi-cloud`
skill. The `$gmi-cloud` examples and `$skill-installer` instructions here target
Codex. `agents/openai.yaml` is Codex metadata; other hosts use `SKILL.md`.

Grok also documents discovery of Claude Code skills, so an existing
`~/.claude/skills/gmi-cloud/` installation can serve both. Antigravity CLI and
OpenCode both support project-local `.agents/skills/gmi-cloud/`; Claude Code's
project location is `.claude/skills/gmi-cloud/`, and Grok's is `.grok/skills/gmi-cloud/`.

All hosts need Python 3.10+, network access, writable job/output storage, and
`GMI_API_KEY` in the helper's environment. Launching a CLI from a shell that has
exported the key passes it to child processes unless the host filters the
environment. The helper does not read `.zshrc` itself. Claude/Grok web chats and
remote sessions do not automatically inherit your local shell environment;
these local CLI instructions do not establish web-app compatibility.

Model discovery, submission, saved async jobs, manual status checks and downloads
use the same helper. **Optional adaptive scheduled checks require separate host
capability checks and remain unverified in these other hosts.** The agent must
use a real compatible scheduler and confirm creation; otherwise it returns the
manual status command. Skill installation alone does not enable monitoring.

## Approval before spending

Before any action that may incur a charge:

1. Prepare the exact model, parameters, and number of outputs.
2. Show the estimated total cost in USD and how it was calculated.
3. Ask for explicit user approval and wait for the reply.
4. Submit only the approved work, once.

If pricing is unknown, disclose that and request approval before submitting.
Any change that increases the approved cost requires new approval.
Never treat model discovery, payload preparation, or a general request
to generate as spending approval.

Read-only catalog, pricing, and status checks may proceed without approval
when those operations are free.


This applies to text inference, media generation and any other potentially billed
operation. A request such as "generate a video" starts preparation and quoting;
it does not authorize submitting a paid request. Approval covers the displayed
model, parameters, output count and cost estimate (or the disclosed unknown price).

This is a skill instruction for the agent. Direct manual helper commands do not
implement an interactive approval gate; run billed commands only after reviewing
and approving the work yourself.

## Submit and return; optional automatic checks

After spending approval, the skill submits a media job once and returns after
GMI accepts it. For a pending job, it offers automatic checking as an optional
next step and provides the ID plus a manual status command. **No schedule is
created unless you explicitly opt in.** Approving generation alone, declining
the offer, or not replying does not enable monitoring.

If you opt in and approve any applicable monitoring cost, it uses the host's
native same-chat scheduler:

- Choose a new delay within **2–5 minutes** after each check, based on observed
  status, elapsed job age and jitter; don't leave a fixed recurring interval.
- Check sooner while processing, longer for an old queued job.
- Stay quiet while pending; download/deliver on success and stop the monitor.
- Stop on terminal failure, errors requiring input, user stop, or a default
  one-hour job-age deadline. Monitoring does not cancel the remote GMI job.

Scheduling needs a compatible host with minute-based follow-ups and access to
Python, credentials, TLS settings, job files and the output folder. Native
scheduled checks consume host usage and may incur charges; their scope and known
or unknown cost are included in the approval summary. If scheduling is unavailable
or cannot change the next delay, the skill says so and gives a manual status
command. It does not silently block or create GitHub Actions/OS cron jobs.

The Python helper prepares the handoff but does not install a scheduler. See
[scheduled follow-up](skills/gmi-cloud/references/follow-up.md) for implementation, platform limits and verification status.

## Requirements

- Python 3.10+ with standard-library TLS support; no pip dependencies.
- An agent host with local `SKILL.md` support and permission to execute Python;
  see [host compatibility](#host-compatibility).
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

74 offline tests pass locally on macOS with Python 3.13. Windows/Linux path logic
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
