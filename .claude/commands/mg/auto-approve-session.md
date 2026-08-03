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

Three independent controls, each with its own sidecar:

- **arm / off** — a 30-minute sliding auto-approval window (suppresses prompts).
- **pause / unpause** — a sticky latch that makes *every* guarded tool call in
  that session ask for approval until released. Sticky on purpose: a one-shot
  marker would be consumed by whichever parallel subagent happened to call a
  tool first, leaving its siblings running.
- **mute-session-limit / unmute-session-limit** — silences the usage-limit
  warning for the *current* window only. The `mg-usage-watch` daemon publishes
  the real limits and the guard asks on every call once they are close, so a run
  stops before walking into a rate-limit cutoff. Muting is how you say "seen it,
  let this window finish"; the next window warns again.

`$ARGUMENTS` may be empty, a session id / prefix, or `off`, `pause`, `unpause`,
`mute-session-limit`, `unmute-session-limit` followed by an id/prefix (`pause`
also takes an optional free-text note).

The script is invoked with plain `python3` (stdlib-only, no venv needed):
`python3 "$(git rev-parse --show-toplevel)/.claude/permission-hooks/scripts/auto-approve-session.py" <subcommand> [args]`

## Step 1 — Direct path (an id/prefix was given in `$ARGUMENTS`)

Route on the first word: `off`, `pause`, `unpause`, `mute-session-limit` or
`unmute-session-limit` → that subcommand on the remaining id/prefix (for `pause`,
pass any remaining words as the note). Anything else → treat `$ARGUMENTS` as an
id/prefix and run `arm`.

Parse the JSON result:
- `ok: true` → tell the user which session was armed / disarmed / paused /
  released / muted / unmuted (`short_id` + `project`). For `arm`, mention
  auto-approval slides for `ttl_minutes` of activity. For `pause`, mention the run
  stays paused until `unpause`. For `mute-session-limit`, mention it covers only
  the current window. If `guard` is not `active`, warn (see Step 2). **Done.**
- `ok: false` → show `error` (e.g. an ambiguous prefix lists the candidates, or no
  usage reading is being published) and stop.

## Step 2 — Picker (no `$ARGUMENTS`)

Run the `list` subcommand and parse the JSON `sessions` array (newest first, ≤10).

If the array is empty, tell the user no other sessions were found and stop.

Otherwise render a numbered list so the user can recognise the target. For each
session show the number, `short_id`, `project`, `last_active`, `armed`, `paused`,
`guard` and `usage`, then what is running now (`activity`, see below), then its
user commands:
- if `commands.condensed` is true → show the single `commands.first` list (the whole
  short session), joined with ` · `;
- otherwise → show `first:` (`commands.first`) and `last:` (`commands.last`) on two
  lines, each joined with ` · `.

`activity` is what the session is working on *right now* — the commands list only
holds what the user typed, so a session whose blocked call comes from a subagent
or a dynamic workflow shows nothing there but a prompt from twenty minutes ago.
Under the header line, add one `▸` line per live thing, and nothing at all when
there is none:
- for each entry in `activity.workflows` → `▸ workflow <name> (<run>) · <agents_live>
  live`. Workflow agents have no individual labels, so the run's name is all there
  is; `agents_live: 0` means the run is between phases at a barrier.
- if `activity.subagents_live` > 0 → `▸ <n> subagent(s) live: ` plus the
  `description`s from `activity.subagents` (newest first, at most 3) joined with
  ` · `. Fall back to `type` for an entry with an empty `description`.

When `guard` is not `active`, add a warning line under that session:
- `deferring` → the session is in a CC-vetted permission mode, so the guard
  stands down there and arming or pausing it would write a file nobody reads.
- `never` → the guard has never run in that session at all.

`usage` is the session's standing with the limit gate: `clear` (under the
thresholds), `gated` (over them, so this session is being asked on every call),
`muted` (over them but silenced for this window), or `unknown` (no fresh reading
— the daemon is not running, so the guard is not gating).

Example rendering:

```
[1] a1b2c3d4 · road_runner · 12s ago · armed: yes · paused: no · guard: active · usage: gated
     ▸ workflow connection-budget-redesign (wf_e94972d4-091) · 4 live
     ▸ 2 subagents live: Research barrier count · Find the eval callers
     first: /gsd:new-milestone · set up the retrieval eval harness · /gsd:plan-phase
     last:  why is DATABASE_URL on prod? · grep eval_extractor · /gsd:execute-phase
[2] 9f8e7d6c · mg-cc-tools · 3m ago · armed: no · paused: no · guard: deferring · usage: clear
     ⚠ CC-vetted permission mode — arm/pause will not fire in this session
     /mg:auto-approve-session · could we improve auto-approve
```

(The top entry is often *this* session — pick the one whose commands match the
run you mean.)

Then ask the user to reply with **the number** to arm, **`p<number>`** to pause,
**`u<number>`** to release a pause, **`m<number>`** to mute the session limit,
**`M<number>`** to unmute it (or `q` to cancel), and **stop — do not choose for
them.** When the user replies, map it to that session's `id` from the list above,
run the matching subcommand, and confirm as in Step 1.

## Notes

- This writes the same sidecars the guard already trusts — it grants no new
  capability, only ergonomics.
- It cannot dismiss a permission prompt already on screen in the target session:
  that call already got its verdict. The user answers that one once (`1. Yes`);
  after that, arming auto-approves and pausing asks again.
- While a session is paused, approving a prompt lets **only that one call**
  through — the next call asks again. Resuming the run means `unpause`, not
  approving. Expect one prompt per active subagent — the `▸` lines are how many
  that is likely to be.
- The `▸` lines say what is *working*, not what is *blocked*: the guard decides in
  process and records nothing, so a session sitting on a prompt shows whichever
  siblings are still running around it. A run whose agents have all stopped
  writing shows no `▸` line and a `last_active` that keeps ageing — that pairing
  is the signal it is waiting on someone.
- `arm`/`off`, `pause`/`unpause` and the mute are independent: pausing leaves an
  armed window in place (the latch is checked first), releasing a pause does not
  disarm anything, and muting the limit warning touches neither.
- The limit gate is checked ahead of the auto-approve window on purpose — an
  armed unattended run is exactly what should not burn the last of a window
  unsupervised. So `arm` does not exempt a session from it; only the mute does.
- Muting needs a fresh reading to key itself to, so `mute-session-limit` fails
  when `mg-usage-watch` is not running. Nothing is gating in that state either.
