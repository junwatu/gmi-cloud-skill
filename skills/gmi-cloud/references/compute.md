# AgentBox and compute boundary

The helper covers inference and media. For requested sandbox/GPU workflows,
consult current official docs and implement only the needed direct HTTP calls.
Keep compute operations separate from the included inference/media helper.

- [Sandbox overview](https://docs.gmicloud.ai/api-reference/sandbox/overview)
- [Create sandbox](https://docs.gmicloud.ai/api-reference/sandbox/create-a-sandbox)
- [Connect](https://docs.gmicloud.ai/api-reference/sandbox/connect-to-a-sandbox)

Compute control-plane credentials differ from an inference-only key. Use
`GMI_COMPUTE_API_KEY` or `GMI_SANDBOX_API_KEY` for compute bearer authentication.
Data-plane calls use fresh `connect` host/token values and `X-Access-Token`;
never send the compute key to a sandbox host.

Provision within the user's authorization, use supported creation idempotency
keys, bound readiness waits, and preserve resource IDs. Stop on platform deletion
and report the reason. Track temporary-resource cleanup and report failures.
Sandbox provisioning, exec and file transfer are not covered by this skill's
offline inference/media verification.

Before any potentially billed compute action, follow
[Approval before spending](../SKILL.md#approval-before-spending): show exact
resources/parameters, quantity, duration assumptions and total USD calculation,
or disclose unknown costs, then wait for explicit approval. Prior approval for
media or inference does not authorize provisioning. Increases require approval.
