---
name: auto-approve-session
description: Arm, pause or release permission-guard for ANOTHER session — pick from a list
allowed-tools: Bash
---

# /mg:auto-approve-session

Control the permission-guard state of a session **other than this one** — e.g. a
GSD run that is blocked on a permission prompt and so can't run a command
itself, or a long autonomous run you want to interrupt for a check-in. Run this
from a second, unblocked CC session and pick the target.

Two independent controls, each with its own sidecar:

- **arm / off** — a 30-minute sliding auto-approval window (suppresses prompts).
- **pause / unpause** — a sticky latch that makes *every* guarded tool call in
  that session ask for approval until released. Sticky on purpose: a one-shot
  marker would be consumed by whichever parallel subagent happened to call a
  tool first, leaving its siblings running.

`$ARGUMENTS` may be empty, a session id / prefix, or `off`, `pause`, `unpause`
followed by an id/prefix (`pause` also takes an optional free-text note).

The script is invoked with plain `python3` (stdlib-only, no venv needed):
`python3 "{MG_INSTALL_AUTO_APPROVE_SESSION_SCRIPT}" <subcommand> [args]`

## Step 1 — Direct path (an id/prefix was given in `$ARGUMENTS`)

Route on the first word: `off`, `pause` or `unpause` → that subcommand on the
remaining id/prefix (for `pause`, pass any remaining words as the note).
Anything else → treat `$ARGUMENTS` as an id/prefix and run `arm`.

Parse the JSON result:
- `ok: true` → tell the user which session was armed / disarmed / paused /
  released (`short_id` + `project`). For `arm`, mention auto-approval slides for
  `ttl_minutes` of activity. For `pause`, mention the run stays paused until
  `unpause`. If `guard` is not `active`, warn (see Step 2). **Done.**
- `ok: false` → show `error` (e.g. an ambiguous prefix lists the candidates) and stop.

## Step 2 — Picker (no `$ARGUMENTS`)

Run the `list` subcommand and parse the JSON `sessions` array (newest first, ≤10).

If the array is empty, tell the user no other sessions were found and stop.

Otherwise render a numbered list so the user can recognise the target. For each
session show the number, `short_id`, `project`, `last_active`, `armed`, `paused`
and `guard`, then its user commands:
- if `commands.condensed` is true → show the single `commands.first` list (the whole
  short session), joined with ` · `;
- otherwise → show `first:` (`commands.first`) and `last:` (`commands.last`) on two
  lines, each joined with ` · `.

When `guard` is not `active`, add a warning line under that session:
- `deferring` → the session is in a CC-vetted permission mode, so the guard
  stands down there and arming or pausing it would write a file nobody reads.
- `never` → the guard has never run in that session at all.

Example rendering:

```
[1] a1b2c3d4 · road_runner · 12s ago · armed: yes · paused: no · guard: active
     first: /gsd:new-milestone · set up the retrieval eval harness · /gsd:plan-phase
     last:  why is DATABASE_URL on prod? · grep eval_extractor · /gsd:execute-phase
[2] 9f8e7d6c · mg-cc-tools · 3m ago · armed: no · paused: no · guard: deferring
     ⚠ CC-vetted permission mode — arm/pause will not fire in this session
     /mg:auto-approve-session · could we improve auto-approve
```

(The top entry is often *this* session — pick the one whose commands match the
run you mean.)

Then ask the user to reply with **the number** to arm, **`p<number>`** to pause,
**`u<number>`** to release a pause (or `q` to cancel), and **stop — do not
choose for them.** When the user replies, map it to that session's `id` from the
list above, run the matching subcommand, and confirm as in Step 1.

## Notes

- This writes the same sidecars the guard already trusts — it grants no new
  capability, only ergonomics.
- It cannot dismiss a permission prompt already on screen in the target session:
  that call already got its verdict. The user answers that one once (`1. Yes`);
  after that, arming auto-approves and pausing asks again.
- While a session is paused, approving a prompt lets **only that one call**
  through — the next call asks again. Resuming the run means `unpause`, not
  approving. Expect one prompt per active subagent.
- `arm`/`off` and `pause`/`unpause` are independent: pausing leaves an armed
  window in place (the latch is checked first), and releasing a pause does not
  disarm anything.
