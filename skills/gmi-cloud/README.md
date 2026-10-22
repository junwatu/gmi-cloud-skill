# GMI Cloud skill — Public Beta

**Status: Public beta (`v0.1.0-beta.6`).** APIs and workflows may change.
Report reproducible issues in the [issue tracker](https://github.com/junwatu/gmi-cloud-skill/issues).

Use GMI Cloud from Codex to discover documented and account-listed models, run
text inference, and create image, video,
or audio generation. Media jobs are saved locally so you can check their status,
resume waiting, and download results later.

The helper calls GMI's HTTP APIs directly.

## Requirements

| Requirement | Details |
|---|---|
| Skill host | Codex with local skill discovery and permission to execute Python |
| Python | Python 3.10 or newer, including standard-library HTTPS/TLS support |
| Credentials | `GMI_API_KEY` for account API listings and generation; public documentation discovery works without it |
| Model access | Access to the selected model and sufficient credits/quota for paid calls |
| Network | HTTPS access to `docs.gmicloud.ai`, `api.gmi-serving.com`, `console.gmicloud.ai`, and returned artifact hosts |
| Local storage | A writable directory for job metadata and downloaded files |

There are **no pip dependencies**. Node.js, Bash, zsh, curl, Docker, and administrator
access are not required. Optional `GMI_ORG_ID` selects an organization.

The helper is designed for Windows, macOS, and Linux. It has been tested natively
on macOS; Windows/Linux path branches have simulated coverage. Native Windows and
Linux runs and live GMI generation remain unverified. Read-only model discovery
was verified on macOS using a trusted CA bundle.

## Install in Codex

1. Download [`gmi-cloud.zip`](https://github.com/junwatu/gmi-cloud-skill/releases/tag/v0.1.0-beta.6) and extract it. The resulting `gmi-cloud` folder must
   contain `SKILL.md`, `scripts/`, `references/`, and `agents/`.
2. Copy the **whole folder**, not only `SKILL.md`, into your user skills folder:

   | OS | Install destination |
   |---|---|
   | macOS / Linux | `~/.agents/skills/gmi-cloud/` |
   | Windows | `%USERPROFILE%\.agents\skills\gmi-cloud\` |

3. In Codex, mention `$gmi-cloud`. If it does not appear, restart Codex.

For a fresh installation, run the following from the folder containing the
extracted `gmi-cloud` directory.

macOS / Linux:

```sh
mkdir -p "$HOME/.agents/skills"
cp -R ./gmi-cloud "$HOME/.agents/skills/"
```

Windows PowerShell:

```powershell
$skillsRoot = Join-Path $HOME '.agents\skills'
New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
Copy-Item -Path '.\gmi-cloud' -Destination $skillsRoot -Recurse
```

For project-only use, copy the folder into `<project>/.agents/skills/gmi-cloud/`
instead. Choose one discovery location to avoid duplicate entries. If your
existing Codex setup already discovers this skill under another configured
location, update that installation rather than adding a second copy.

When updating, replace the installed skill folder with the new extracted folder.
Do not nest it as `gmi-cloud/gmi-cloud`. Job state is stored separately, so replacing
skill files does not remove saved jobs.

These local discovery locations follow the
[official Codex skill documentation](https://learn.chatgpt.com/docs/build-skills).
Other skill hosts may have different installation paths and execution permissions;
this bundle does not claim tested integration with them.

## Install from GitHub

Ask Codex to install the public beta using the built-in skill installer:

```text
Use $skill-installer to install gmi-cloud from
https://github.com/junwatu/gmi-cloud-skill/tree/v0.1.0-beta.6/skills/gmi-cloud
```

The URL points directly to the skill folder and pins the beta release.
Use `main` instead of the tag only if you want the current development version.

A convenient repository layout is:

```text
REPO/
└── skills/
    └── gmi-cloud/
        ├── README.md
        ├── SKILL.md
        ├── agents/
        ├── references/
        └── scripts/
```

The installer handles downloading and copying the complete skill folder. Public
repositories normally need no GitHub credentials. Private repositories require
access through existing Git credentials or a GitHub token available to the
installer. This is separate from the `GMI_API_KEY` used for GMI requests.

The built-in installer defaults to `$CODEX_HOME/skills`, or `~/.codex/skills` when
unset. This can differ from the manual discovery location above; choose one
installation method to avoid duplicate entries. It refuses to overwrite an
existing skill folder. Review the existing installation before replacing it.
For a reproducible installation, use a release tag or commit SHA instead of a
moving branch. The skill should be available on the next Codex turn; restart
Codex if it does not appear.

## Configure credentials

Set `GMI_API_KEY` in the environment available to Codex's Python execution process.
Do not paste the key into chat, include it in a payload file, or commit it.

For a terminal session, enter it without displaying it:

macOS zsh:

```zsh
read -rs 'GMI_API_KEY?GMI API key: '; export GMI_API_KEY; printf '\n'
```

Linux Bash:

```bash
read -rs -p 'GMI API key: ' GMI_API_KEY; export GMI_API_KEY; printf '\n'
```

Windows PowerShell:

```powershell
$secureKey = Read-Host 'GMI API key' -AsSecureString
$env:GMI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
Remove-Variable secureKey
```

These settings last for the terminal session. For persistent use, configure the
launching app's environment or your OS's user environment settings; in CI, use
secret injection. A shell profile such as `.zshrc` only applies when the launching
process loads it. An already running desktop app may need restarting. The helper
does not automatically read `.env` files or execute shell startup files.

More details: [cross-platform setup](references/portability.md).

## Check your setup

Verify Python is 3.10 or newer, then run the helper from the installed skill folder.

macOS / Linux:

```sh
python3 --version
python3 "$HOME/.agents/skills/gmi-cloud/scripts/gmi_api.py" doctor
```

Windows PowerShell:

```powershell
py -3 --version
py -3 "$HOME\.agents\skills\gmi-cloud\scripts\gmi_api.py" doctor
```

If `py` is unavailable, use a verified Python 3.10+ `python` executable.
`doctor` makes no network request and prints no credential values. Check for
`"credentials_available": true`. Also review the `tls` diagnostics. This confirms availability, not whether GMI
accepts the key. Ask Codex to use `$gmi-cloud` to list models to verify API access.

## Certificate setup

The helper uses Python's trusted certificates and keeps TLS verification enabled.
If setup fails with `TLS_CERTIFICATE_VERIFY_FAILED`, follow the
[platform-specific certificate guide](references/portability.md#tls-certificates):

- **macOS, python.org installation:** run the matching `Install Certificates.command`.
- **Linux:** install/update the distribution's `ca-certificates` package.
- **Windows:** check Windows/Python trust and corporate proxy certificates.

For an approved PEM CA bundle, set `GMI_CA_BUNDLE` to its absolute file path.
Python's standard `SSL_CERT_FILE` and `SSL_CERT_DIR` settings are also supported
when `GMI_CA_BUNDLE` is unset. This applies to API calls and artifact downloads.
Use only trusted bundles; custom bundles replace the helper's default trust roots.
The helper never disables verification or changes the machine's trust store.

`doctor` now reports TLS settings, CA count and default trust paths. An offline
check alone does not prove connectivity; retry model listing after repairing TLS.

## Find all current and named models

Run from the installed skill folder:

```sh
python3 scripts/gmi_api.py models --out ./gmi-models.json
python3 scripts/gmi_api.py models --search "WAN 3.0" --details
python3 scripts/gmi_api.py models --search "Seedance 2.5" --details
python3 scripts/gmi_api.py models --kind text
```

On Windows replace `python3` with `py -3`. `models` and its alias `catalog` query:

1. GMI's [official model quickstart index](https://docs.gmicloud.ai/llms.txt).
2. The account's [inference model API](https://docs.gmicloud.ai/inference-engine/api-reference/llm-api-reference).
3. The account's [media model API](https://docs.gmicloud.ai/inference-engine/api-reference/video-api-reference).

The merged result preserves public documentation entries even when the current
API key does not list them, and API entries without public quickstarts. There is
no stored list or default result cap. The exported JSON is complete for the
successful queried sources; chat previews must be labeled as previews.

Search ignores spaces, punctuation and case, using current IDs and documentation
names. `--details` adds matching media metadata; narrow the search to avoid
hundreds of detail requests. `--api-only` explicitly skips public documentation.

Without a key, public documentation is still shown and missing account coverage
is reported as `complete: false` with exit code 1. Failed sources never silently
turn into "GMI has no models". The result includes errors, warnings, source counts,
exact API IDs and documentation URLs. Documentation-only entries have `id: null`;
read the linked quickstart for an explicit executable ID rather than guessing it.

**Compatibility change in beta.6:** `models` is combined discovery by default.
Use `text-models` for the former raw inference `{data: [...]}` JSON response.
`media-models` still returns the raw media list.

Zero workers or inactive status snapshots do not hide a model or locally block
an authorized submission. Worker counts are telemetry; the official request API
decides acceptance. A documented offering is separate from generation access.
Private, regional, dedicated or newly announced offerings can need separate
endpoint/account access. If an official model page is missing from discovery,
use that page to investigate; don't conclude GMI does not offer the model.

See [catalog coverage and recovery](references/catalog.md) for merge rules,
full exports, partial failures, unsupported pagination signals and coverage limits.

## Use the skill

Example Codex requests:

```text
Use $gmi-cloud to discover models from official docs and both account APIs, then save the full catalog.
Use $gmi-cloud to find an active video model and show its parameters and pricing.
Use $gmi-cloud to generate a video with MODEL_ID using this prompt: ...
Use $gmi-cloud to check my saved media jobs and resume waiting for scene-01.
```

The agent inspects the chosen model's current schema before submitting. Listing
models or designing a workflow does not submit a paid generation.

For manual media operation, run these commands from the installed skill folder.
Replace `MODEL_ID`, and create UTF-8 `payload.json` using that model's schema:

```sh
python3 scripts/gmi_api.py model MODEL_ID
python3 scripts/gmi_api.py submit --model MODEL_ID --payload-file payload.json --job-id scene-01
python3 scripts/gmi_api.py wait scene-01 --timeout 45
python3 scripts/gmi_api.py status scene-01
python3 scripts/gmi_api.py download scene-01 --out ./generated-media
```

On Windows, replace `python3` with `py -3`. Pending jobs return exit code 3;
terminal failures return 1 and successful jobs return 0. A timeout or Ctrl+C stops
local waiting while the remote job may continue. Resume the saved ID; do not
resubmit it. There is no background watcher or remote cancellation command.

Submission failures with uncertain acceptance are saved for reconciliation;
paid POSTs are never automatically retried. See [media job recovery](references/media.md)
for `requests` and `attach`, download handling, and all exit codes.

## Data storage

| OS | Default job directory |
|---|---|
| Windows | `%LOCALAPPDATA%\gmi-skill\jobs` |
| macOS | `~/Library/Application Support/gmi-skill/jobs` |
| Linux | `$XDG_STATE_HOME/gmi-skill/jobs`, otherwise `~/.local/state/gmi-skill/jobs` |

Set `GMI_SKILL_STATE_DIR` or pass `--state-dir PATH` **before the subcommand** to
choose another location. Existing legacy registries can be reused automatically;
`doctor` shows the effective location.

Metadata contains request IDs, outcomes, and artifact URLs, not API keys or raw
submitted prompts. Treat result URLs as private. POSIX uses private file modes;
Windows inherits directory ACLs. Store files in a user-controlled directory.

## Tests and scope

Tests run manually; this repository does not configure automatic GitHub Actions.

Run from the skill folder:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
```

On Windows, use `py -3`. The 64 offline tests use a local HTTP fixture and require
no GMI key or credits. They cover async recovery, failures, retries, download
integrity, credential redaction, and portability behavior.

The helper implements text inference and media jobs. Compute/AgentBox guidance
is included as a reference, but sandbox creation, execution, file transfer, media
uploads, and text streaming are not implemented by this helper.
