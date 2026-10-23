# Return after acceptance; offer optional variable follow-ups

For approved media work, the default is to submit once and return after GMI
acknowledges it. Do not chain `wait` or keep the chat turn alive with sleeps.
The initial POST still needs an HTTP response to establish the request ID;
synchronous models may finish inside that response. A request without a
confirmed ID must be reconciled, not automatically resubmitted or monitored.

## Offer monitoring; do not enable it by default

For a pending job, report the confirmed ID and manual status command, then offer
automatic checking. No reply, declining, or only approving generation means no
schedule is created. An offer can say:

> The job is submitted. You can check it manually, or I can enable automatic
> checks at variable 2–5 minute intervals for up to one hour from submission.
> Scheduled checks consume host usage; their cost is unknown unless your plan
> provides a confirmed rate. Would you like automatic checks enabled?

Tailor the disclosure to actual known pricing instead of always claiming it is
unknown. Keep the offer concise. If the user already explicitly opted in and
approved that monitoring scope/cost with the generation plan, do not ask again.
Terminal jobs should be delivered/reported directly without a monitor offer.

## Approval includes monitoring scope

Before spending, show the model/payload/output count and the generation estimate.
Only if monitoring is requested, add its follow-up plan: variable checks within 2–5 minutes, a default one-hour
monitoring window from submission, output folder, and completion-only reporting.
Scheduled agent wakes consume host usage and may incur charges under the user's
plan. Disclose the estimated monitoring cost if known, or that it is unknown,
and obtain explicit approval as required by [the spending policy](../SKILL.md#approval-before-spending).
Do not describe scheduling as universally free. If only generation was approved,
do not add potentially charged monitoring without its approval.

## Prepare the offline handoff

Only after scheduling opt-in and any required spending approval for a confirmed
pending job, run:

```sh
python3 <skill-dir>/scripts/gmi_api.py follow-up JOB_ID --out OUTPUT_DIR
```

Use a verified Python 3.10+ interpreter (`py -3` on Windows where available).
`follow-up` only reads the saved job. It creates no schedule, makes no API call,
waits for no job, and never submits work. `schedule_confirmed: false` is deliberate.
The returned argument arrays contain absolute interpreter/helper/state/output
paths; run them as arguments with correct host-shell quoting, not as eval text.
No secret values or artifact URLs are embedded in the scheduler prompt.

For pending jobs, the plan gives `next_check_minutes`, a range, `deadline_at`,
`prompt`, and `followup_argv` / `status_argv` / `download_argv`.
The next delay is recomputed from saved status, elapsed job age and jitter:

| Observed state | Default next delay |
|---|---|
| Recently queued/created/pending | Randomly chosen within 2–5 minutes |
| Still queued after 10 minutes | 4–5 minutes |
| Dispatched/processing/running | 2–3 minutes |

This uses observed state, not a claimed model completion prediction. Repeated
checks may occasionally choose the same delay; the schedule is recalculated each
time rather than left on a fixed recurrence. Customize approved bounds with
`--min-check-minutes`, `--max-check-minutes`; `--max-minutes` changes the overall
window. Re-running the plan preserves its deadline relative to `created_at`.
The final scheduler wake can occur after the deadline, but it must stop without
another API lookup. Sleeping machines and host scheduling delays affect timing.

## Create the actual schedule using the host

First verify explicit scheduling opt-in and applicable spending approval. Merely
producing or inspecting the offline plan is not authorization to create a monitor.

1. Discover the available native scheduling capability and its current schema.
   In Codex desktop with `codex-app-tools`, use `automation_update` and a heartbeat
   returning to this same chat. A skill folder alone is not a scheduler.
2. Confirm the scheduler can execute Python and access the same helper, job state,
   output folder, credentials and trust configuration. `required_environment`
   contains variable names only; do not paste secret values into saved prompts.
   Scheduled executions have their own sandbox; current-turn permissions or shell
   startup settings do not guarantee unattended access.
3. Look for a matching existing monitor by request ID and absolute state path.
   Reuse/update it rather than create duplicates. Preserve the host-returned ID.
4. Create/update the same-chat follow-up for the plan's next delay, using its
   durable prompt. Use the host scheduling tool, not hand-written automation
   files/directives, shell daemons, OS cron, or GitHub Actions. Do not create a
   separate chat per check unless the user explicitly requests that behavior.
5. Only after the tool confirms creation/update, tell the user the request ID,
   next expected check, variable range, deadline and where results will appear.
   Keep the task prompt scoped to this existing request.

The scheduler should execute the following logic on every wake:

- Run `followup_argv` offline first. If it says to stop, handle that outcome and
  disable the monitor; do not perform another status lookup after the deadline.
- For `schedule_required`, run `status_argv` once. Exit 3 means pending. Stay quiet,
  run the offline plan again using the newly saved status, and **update the same
  monitor** to the returned next delay. Do not keep its original interval.
- On success, download using `download_argv`, present the actual files once and
  disable the monitor. If another invocation already finished the job, the
  offline plan can directly return `download` or `report_failure`.
- Stop and notify on terminal failure, unknown status, deadline, missing resources,
  credential/TLS/network errors or partial download failure. Preserve the IDs and
  give resume instructions. Do not silently restart a failed monitoring loop.
- Never submit, regenerate, repeat a paid POST, expand the spending scope, or
  archive the user's chat. A stopped monitor does not cancel GMI's remote job.
- Honor an explicit user stop. Report only completion, failure or required input;
  pending-to-pending changes do not need messages.

On a terminal state, the helper returns `stop_monitoring: true` and an action:
`download`, `report_failure`, `needs_attention`, `reconcile_submission` or
`deadline_reached`. It never claims to have disabled a native automation itself.
Cleanup must use the actual scheduler tool and be confirmed by it.

## Host limitations and verification

The official [scheduled tasks documentation](https://learn.chatgpt.com/docs/automations)
describes minute-based follow-ups inside an existing chat. Local tasks need the
computer on, the app running and files accessible. CLI/IDE-only environments may
lack scheduling controls; web/cloud tasks cannot automatically read local paths.
Native scheduling availability, allowed cadence and edit support must be checked
in the actual host. A successful offline handoff is not a scheduled-task test.

If there is no suitable scheduler, it cannot update variable delays, or creation
fails, report that monitoring is not active and return the saved job ID plus a
manual `status` command. Do not silently start a blocking `wait`. Use bounded
`wait` only when the user explicitly asks to wait in the current turn.

Default planning and stop behavior are covered by local fixture tests. A live
monitor was not created while developing this update because no approved real
media job was submitted. No scheduler or automation is installed on importing or
installing this skill; scheduling happens only for an explicitly opted-in pending
job after any required spending approval.
