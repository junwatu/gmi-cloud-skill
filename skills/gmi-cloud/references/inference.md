# Text inference

Use `python3 <skill-dir>/scripts/gmi_api.py` below as `HELPER`.

```sh
HELPER catalog
HELPER catalog --kind text --search "MODEL NAME"
HELPER models
HELPER chat --model MODEL_ID --prompt 'Explain this error' --max-tokens 512
HELPER chat --model MODEL_ID --messages-file conversation.json --max-tokens 512
```

`conversation.json` is a JSON array of chat messages. Prompt files can be passed
with `--prompt-file PATH`. Exactly one input is required. The helper sends
non-streaming `POST /v1/chat/completions` and returns the response as JSON.
It never retries paid POSTs. Read-only discovery retries transient failures
at most twice. No model is hard-coded as a default.

Credentials are `GMI_API_KEY` and optional `GMI_ORG_ID`. API requests use explicit
User-Agent and bearer auth over HTTPS. API redirects are rejected so credentials
cannot follow redirects. Errors redact the current key and credential fields.
Do not echo keys from shell environment tools.

Source: [GMI LLM reference](https://docs.gmicloud.ai/inference-engine/api-reference/llm-api-reference),
consulted 2026-10-23. Check current docs when models reject parameters. Read-only model discovery was verified on macOS with a trusted CA bundle.
Live text generation remains unverified.

`models` returns only the inference endpoint catalog. For all currently listed
text and media entries, use `catalog`. It fetches both sources on every call and
reports source counts and errors. Listing order is not a release-date ranking.
