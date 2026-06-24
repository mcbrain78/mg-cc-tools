---
name: auto-approve-session
description: Arm (or clear) permission-guard auto-approval for ANOTHER session — pick from a list
allowed-tools: Bash
---

# /mg:auto-approve-session

Arm the permission-guard auto-approval flag for a session **other than this one** —
e.g. a GSD run that is blocked on a permission prompt and so can't run a command
itself. Run this from a second, unblocked CC session, pick the target, and it arms
that session's 30-minute sliding auto-approval window.

`$ARGUMENTS` may be empty, a session id / prefix, or `off <id-prefix>`.

The script is invoked with plain `python3` (stdlib-only, no venv needed):
`python3 "$(git rev-parse --show-toplevel)/.claude/permission-hooks/scripts/auto-approve-session.py" <subcommand> [args]`

## Step 1 — Direct path (an id/prefix was given in `$ARGUMENTS`)

- If `$ARGUMENTS` starts with `off`, run the `off` subcommand on the remaining id/prefix.
- Otherwise treat `$ARGUMENTS` as an id/prefix and run the `arm` subcommand.

Parse the JSON result:
- `ok: true` → tell the user which session was armed/disarmed (`short_id` + `project`),
  and that auto-approval slides for `ttl_minutes` of activity. **Done.**
- `ok: false` → show `error` (e.g. an ambiguous prefix lists the candidates) and stop.

## Step 2 — Picker (no `$ARGUMENTS`)

Run the `list` subcommand and parse the JSON `sessions` array (newest first, ≤10).

If the array is empty, tell the user no other sessions were found and stop.

Otherwise render a numbered list so the user can recognise the target. For each
session show the number, `short_id`, `project`, `last_active`, and `armed` status,
then its user commands:
- if `commands.condensed` is true → show the single `commands.first` list (the whole
  short session), joined with ` · `;
- otherwise → show `first:` (`commands.first`) and `last:` (`commands.last`) on two
  lines, each joined with ` · `.

Example rendering:

```
[1] a1b2c3d4 · road_runner · 12s ago · armed: no
     first: /gsd:new-milestone · set up the retrieval eval harness · /gsd:plan-phase
     last:  why is DATABASE_URL on prod? · grep eval_extractor · /gsd:execute-phase
[2] 9f8e7d6c · mg-cc-tools · 3m ago · armed: yes
     /mg:auto-approve-session · could we improve auto-approve
```

(The top entry is often *this* session — pick the one whose commands match the
blocked run.)

Then ask the user to **reply with the number** to arm (or `q` to cancel), and
**stop — do not choose for them.** When the user replies with a number, map it to
that session's `id` from the list above and run the `arm` subcommand on that id,
then confirm as in Step 1.

## Notes

- This writes the same sidecar the guard already trusts — it grants no new
  capability, only ergonomics.
- It cannot dismiss a permission prompt already on screen in the target session:
  that call already got its verdict. The user answers that one once (`1. Yes`);
  every guarded action after it auto-approves.
- To disarm early: `/mg:auto-approve-session off <id-prefix>`.
