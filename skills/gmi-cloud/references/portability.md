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

## TLS certificates

The helper verifies server certificates and hostnames for both API requests and
artifact downloads. It uses Python's default trust setup, including supported
`SSL_CERT_FILE` / `SSL_CERT_DIR` settings. Optionally set `GMI_CA_BUNDLE` to an
absolute path to a trusted PEM CA bundle; it takes precedence and replaces the
default trust roots for this helper. For corporate proxies, use a bundle supplied
by your organization containing the required public and corporate CA certificates.
Do not download an arbitrary certificate bundle from an untrusted source.

`doctor` reports verification settings, loaded CA count and resolved default
certificate paths offline. A zero count can indicate missing trust roots, but
some CA directories load certificates lazily, so the count alone is not a network
test. Test actual connectivity using `models` after configuration.

`TLS_CERTIFICATE_VERIFY_FAILED` means a server certificate could not be verified;
it can indicate missing roots, an expired certificate, hostname mismatch, a wrong
system clock, or a TLS-intercepting proxy. `TLS_CA_CONFIG` means the configured
trust files could not be loaded. Certificate failures are not retried as transient
network errors. For an uncertain media submission, reconcile the saved job before
any new submission even after TLS is repaired.

### macOS

For Python installed from python.org, finish certificate setup using
`/Applications/Python 3.X/Install Certificates.command` for the actual Python
version running the helper. This installer step may download certificates; it is
not a runtime dependency of the skill. For Homebrew/Conda Python, use that
distribution's certificate setup instead.

As a per-process alternative, if `/etc/ssl/cert.pem` exists and is the trusted
system bundle for the machine:

```sh
GMI_CA_BUNDLE=/etc/ssl/cert.pem python3 scripts/gmi_api.py models
```

This path is a macOS-specific option, not a default imposed on other OSes.

### Linux

Ensure the distribution's `ca-certificates` package is installed and current,
including in minimal container images. Use the distribution's normal trust-store
tools for organization CAs. If the Python installation does not find that store,
set `GMI_CA_BUNDLE` to its verified PEM bundle path; locations vary by distribution.
For example, Debian/Ubuntu commonly use `/etc/ssl/certs/ca-certificates.crt`.

### Windows

Python's default SSL setup loads supported Windows certificate stores. Update
Windows/Python certificate configuration, and check whether corporate proxy CAs
are installed for the account running the helper. For a trusted PEM bundle:

```powershell
$env:GMI_CA_BUNDLE = 'C:\certificates\approved-ca-bundle.pem'
py -3 scripts/gmi_api.py models
```

The bundle path must be available in the executor's environment too. Restart or
relaunch a desktop app when necessary for environment changes to take effect.
There is no insecure TLS bypass option and no automatic trust-store modification.

Sources: [Python SSL defaults](https://docs.python.org/3/library/ssl.html#ssl.create_default_context)
and [python.org macOS certificate setup](https://docs.python.org/3.13/using/mac.html).

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
