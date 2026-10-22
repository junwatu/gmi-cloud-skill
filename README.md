# GMI Cloud Skill — Public Beta

![Public beta](https://img.shields.io/badge/status-public%20beta-orange)

A Codex skill for GMI Cloud model discovery, text inference, and resumable image,
video, and audio generation. Written in Python using only the standard library.

**Version: `v0.1.0-beta.1`.** Expect changes while API behavior and platform support
are validated. This is an independent community project, not an official GMI Cloud product.

## Install

Ask Codex:

```text
Use $skill-installer to install gmi-cloud from
https://github.com/junwatu/gmi-cloud-skill/tree/v0.1.0-beta.1/skills/gmi-cloud
```

Or download `gmi-cloud.zip` from the
[beta release](https://github.com/junwatu/gmi-cloud-skill/releases/tag/v0.1.0-beta.1)
and follow the [manual installation guide](skills/gmi-cloud/README.md#install-in-codex).

## Requirements

- Python 3.10+ with standard-library TLS support; no pip dependencies.
- Codex with local skill support and permission to execute Python.
- `GMI_API_KEY` available to the Python process; optional `GMI_ORG_ID`.
- Network access to GMI endpoints and artifact hosts, writable local storage,
  and GMI model access/credits for paid requests.

See the [complete setup and usage guide](skills/gmi-cloud/README.md).

## Async media jobs

Submit once, save the request ID, and resume status polling later. The helper
handles immediate and asynchronous failures, bounded waiting, rate limits,
uncertain submission acceptance, and artifact downloads with integrity checks.
It does not automatically retry paid submissions. Stopping local waiting does
not cancel remote work; there is no background monitoring daemon.

## Beta verification

34 offline tests pass locally on macOS with Python 3.13. Windows/Linux path logic
has simulated coverage. CI is configured for Windows, macOS, and Linux with
Python 3.10 and 3.13, but the initial jobs could not start because GitHub reported
an account billing lock. No native Windows/Linux CI results are available yet.
See the [initial CI run](https://github.com/junwatu/gmi-cloud-skill/actions/runs/39844807249).
Live GMI requests, provisioning, and media uploads have not been verified here.
The helper implements inference and media, with compute guidance as reference only.

From the repository root:

```sh
python3 -m unittest discover -s skills/gmi-cloud/scripts -p 'test_*.py'
```

On Windows, use `py -3` in place of `python3`.

Report issues with OS, Python version, command, and sanitized error output.
Never include API keys, private prompts, signed artifact URLs, or job-state files.
