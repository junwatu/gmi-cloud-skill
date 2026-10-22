# Windows, macOS, and Linux

The helper uses Python 3.10+ and its standard library. Invoke the script through
an available Python interpreter. Verify its version rather than assuming
`python` means Python 3.

| Host | Usual interpreter | Default job directory |
|---|---|---|
| Windows | `py -3` or verified `python` | `%LOCALAPPDATA%\gmi-skill\jobs` |
| macOS | `python3` | `~/Library/Application Support/gmi-skill/jobs` |
| Linux | `python3` | `$XDG_STATE_HOME/gmi-skill/jobs`, otherwise `~/.local/state/gmi-skill/jobs` |

On Windows, absent `LOCALAPPDATA` falls back to `~/AppData/Local`. A relative
`XDG_STATE_HOME` is ignored. `--state-dir PATH` overrides `GMI_SKILL_STATE_DIR`,
which overrides the native default. If an old `~/.local/state/gmi-skill/jobs`
registry exists and the native directory does not, that registry is reused;
there is no automatic migration or copying of private job metadata.

## Environment setup

Credentials come from the Python process's environment. The skill does not source
`.zshrc`, `.bashrc`, PowerShell profiles or arbitrary shell code. Startup-file
settings only help when the launching process actually loads them. A desktop app
already running may need to be restarted after persistent environment changes;
use its supported environment settings or launch it from a configured shell.

Configure `GMI_API_KEY` through the host's secrets/environment UI when available.
For a manual terminal session, these commands read it without displaying it or
putting it directly in shell history (do not run them with shell tracing enabled):

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

These are session settings. In CI/containers, inject `GMI_API_KEY` as a secret.
Optional organization routing uses `GMI_ORG_ID` on every platform. Never print
the complete environment to diagnose credential availability.

## Run and diagnose

POSIX shell (replace the example path with the installed skill path):
```sh
python3 "/path with spaces/gmi-cloud/scripts/gmi_api.py" doctor
```

Windows PowerShell:
```powershell
py -3 "C:\path with spaces\gmi-cloud\scripts\gmi_api.py" doctor
```

Use UTF-8 JSON for payloads/messages; a UTF-8 BOM is accepted. Prompt files also
use UTF-8. Stdout JSON escapes Unicode for older consoles; JSON parsers recover
the original characters. Job IDs must be portable filenames; avoid Windows
device names such as `CON`/`NUL`/`COM1`, trailing dots, and path separators.
Lowercase IDs avoid case-sensitivity differences between filesystems.

Paths are handled with `pathlib`. If a host has restrictive path-length limits,
select a short `--state-dir` and output directory. A sandbox or remote executor
uses its own environment and filesystem, not necessarily the desktop user's.

POSIX file modes are 600, new registry directories 700. Windows does not gain
Unix-mode privacy from these flags: state and downloaded files inherit the
account directory's ACLs. Keep them in a user-controlled folder; the helper does
not alter Windows ACLs or require administrator access.

## Verification limits

The offline suite covers OS path-selection branches, reserved names, UTF-8/BOM,
Unicode JSON, credential diagnostics, and async workflows. It was run natively
on macOS. Windows/Linux branches tested on macOS are simulations, not proof of
native compatibility. Before publishing a supported-platform guarantee, run:

```text
python -m unittest discover -s scripts -p "test_*.py"
```

Run it from the skill folder using Python 3.10+ on each actual OS. It uses a local
HTTP fixture and makes no paid GMI requests. TLS/proxy and real GMI behavior still
require a separate live check with a configured account.
