# Text inference

Use `python3 <skill-dir>/scripts/gmi_api.py` below as `HELPER`.

```sh
HELPER models --kind text
HELPER text-models
HELPER chat --model EXACT_API_ID --prompt 'Explain this error' --max-tokens 512
HELPER chat --model EXACT_API_ID --messages-file conversation.json --max-tokens 512
```

`models --kind text` combines current official text quickstarts and the account's
inference listing. `text-models` returns the raw inference endpoint JSON. For
all modalities, use plain `models`. See [catalog discovery](catalog.md) for
source coverage, alias lookup and complete exports. A documentation-only title
is not necessarily an executable ID: read the official quickstart to resolve it.

Before running `chat`, follow [Approval before spending](../SKILL.md#approval-before-spending).
Show the exact model, input/messages and parameters, number of requests/outputs,
and the USD estimate with its calculation. For token billing, state input/output
rates and estimated token counts; separate estimates from a guaranteed cap.
If pricing or output usage is uncertain, disclose it and wait for explicit
approval of that uncertainty. A general request for a response is not approval.

`conversation.json` is a nonempty array of role/content chat messages. Prompt
files can be passed with `--prompt-file PATH`. Exactly one input is required.
The helper sends non-streaming `POST /v1/chat/completions` and returns its JSON.
It never retries paid POSTs. Read-only API discovery retries transient failures
at most twice. There is no hard-coded default model or allowed-model list.

Use `GMI_API_KEY` and optional `GMI_ORG_ID`. API requests use explicit User-Agent,
bearer auth, and HTTPS; API redirects are rejected. Errors redact known secrets
and credential fields. Never print the shell environment to diagnose credentials.
Public documentation discovery remains available without an API key; text
inference and raw account listings require one.

Source: [GMI LLM reference](https://docs.gmicloud.ai/inference-engine/api-reference/llm-api-reference),
reviewed 2026-10-23. Check current per-model docs when parameters are rejected.
Read-only discovery was verified live with a trusted CA bundle; paid text
inference remains unverified by this skill's tests.
