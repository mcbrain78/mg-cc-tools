# Spec Improve Auto

---
name: mg-temp:spec-improve-auto
description: Autonomous workflow-driven refinement of a concept spec — one drain run per invocation, decisions reviewed post-hoc via a deterministic briefing
argument-hint: "<file-path>"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - Workflow
---

<objective>
Refine a concept spec autonomously. Each invocation drives **one drain run** through the Workflow tool: a horizontal macro pass stabilizes the skeleton, a verification pyramid verifies typed atoms and disposes of findings, and an exit exam confirms convergence. Decision-shaped findings do not stop the run — they are researched and **auto-taken**, written as D-blocks, and logged as decision records.

This command orchestrates; the drain executes. The user reviews **decisions, not rounds**: after each run the command presents a deterministic **decision briefing** plus a scorecard, and the user accepts, overrides a decision, or raises an editorial directive — each collected structurally and fed to a scoped re-run. The safety net is unchanged: every edit lands on the working copy, the original changes only on explicit approve, and fixes and non-goals are approved independently.
</objective>

<context>
Arguments: $ARGUMENTS

Expected: a path to the concept spec to refine (typically `docs/work-queue/todo/{name}/concept.md`).

Concept spec template: `{MG_INSTALL_CONCEPT_TEMPLATE}`

File-operations script: `{MG_INSTALL_SCRIPTS_DIR}/improve_files.py`

Checks / derivation script: `{MG_INSTALL_SCRIPTS_DIR}/spec_checks.py`

Drain workflow: `{MG_INSTALL_WORKFLOWS_DIR}/spec-improve-auto.js`
</context>

<process>

## Setup (cold-start entry only)

1. Parse `$ARGUMENTS` to get the target file path. If missing:
   ```
   ERROR: File path required.

   Usage: /mg-temp:spec-improve-auto <file-path>

   Example:
     /mg-temp:spec-improve-auto docs/work-queue/todo/worktrees/concept.md
   ```
   Exit.

2. Read the target file. If it doesn't exist or is empty, report the error and exit.

3. **Guarded init.** Run:
   ```
   uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py init <target-file-path>
   ```
   - **On success (exit 0):** capture the emitted JSON — the resolved paths object (`source`, `auto_improve`, `atoms`, `decisions`, `implementer_notes`, `changelog`, `non_goals`, `history_dir`, `next_run`, the `*_exists` flags, `original_backup`, `backup_created`). Store it as `PATHS_JSON`. If `backup_created` is true, report: `Backed up original to <original_backup>`.
   - **On guard-fail (exit 1):** a working copy already exists (the D7 guard). Do **not** overwrite it blindly. Run the read-only:
     ```
     uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py paths <target-file-path>
     ```
     to get the resolved-paths JSON. Surface the leftover state to the user (there is an in-progress working copy from a prior session), then use **AskUserQuestion** for the binary choice:
     - **Resume** — continue with the existing working copy. Use the `paths` JSON as `PATHS_JSON`.
     - **Discard and restart** — run `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py init <target-file-path> --fresh`, then use its JSON as `PATHS_JSON`.

     This AskUserQuestion is the **only** picker in the command. All later decision discussion is prose, never a picker.

**CRITICAL: All modifications happen exclusively on the working copy (`auto_improve`). The original is never touched until the user explicitly approves via `improve_files.py approve`.**

## Path absolutization + scratch dir (before the first Drain invocation)

4. **Get cwd.** Run a Bash `pwd`. The command runs in the main session, whose cwd is reliably the project root.

5. **Absolutize every path that crosses into the drain.** Rule: if a path does not begin with `/`, prepend `<cwd>/`; this is a no-op on an already-absolute `--global`/`--target` path. Absolutize:
   - `scriptPath` = `{MG_INSTALL_WORKFLOWS_DIR}/spec-improve-auto.js`
   - `scripts_dir` = `{MG_INSTALL_SCRIPTS_DIR}`
   - `template_path` = `{MG_INSTALL_CONCEPT_TEMPLATE}`
   - **every path value inside `PATHS_JSON`** (`source`, `auto_improve`, `atoms`, `decisions`, `implementer_notes`, `changelog`, `non_goals`, `history_dir`)

   The command's **own** `uv run {MG_INSTALL_SCRIPTS_DIR}/…` calls stay **relative** — they execute in the main session, so their cwd is known. Only the paths handed to the drain are absolutized (the drain's spawned agents have an undocumented cwd).

6. **Create the scratch dir.** Run a Bash `mkdir -p` for an absolute scratch directory under the session scratch path (this is drain scratch — where the drain's agents marshal relayed values to files for scripts; keep it out of the spec's directory). Record its absolute path as `SCRATCH_DIR`.

## Drain run

7. Invoke the drain, passing the args object (see **Args object** below):
   ```
   Workflow({ scriptPath: <absolutized scriptPath>, args: <args object> })
   ```

## On return — branch on `status`

The return is thin: `{ status, rounds, fixed, below_bar }` only. `status` is the one value only the workflow can supply; the three counts are **this-run** (per-invocation) accumulators (`fixed` = auto-fixable findings applied, **not** decision-takes). Everything about **decisions and atoms** the command derives itself, after return, from the on-disk sidecars (see **Command-side derivation**).

### `converged`
Present, in order:
1. **Decision briefing** — `uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py briefing <decisions-path>` (deterministic, dependency-ordered, blast-radius-ranked, `review_first` items first).
2. **CHANGELOG summary** — read `<changelog-path>` and summarize the run's entries.
3. **Scorecard** — see **The scorecard**.

Then run the **approval / override / directive flow**:
- **Accept** → approve fixes and proposed non-goals **independently**:
  - `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py approve <target-file-path>`
  - for each accepted proposed non-goal: `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py append-non-goal <target-file-path> "<non-goal text>"`
  - (to reject the fixes instead: `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py reject <target-file-path>`)
  - Acceptance ends the loop.
- **Override a decision** → collect a structured `overrides` entry `{ "decision_id": "<id>", "directive": "<free-form override text>" }` (the id is known — the command presented that specific card). Re-run (see **Re-run / re-entry rule**).
- **Editorial non-decision change** ("section 4's approach is wrong, redo it") → collect a free-form `directives` entry. Re-run.

### `blocked`
The drain hit ≥1 untakeable decision (D5's graded gate). Present:
- the **blocked cards** — from `uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py decisions summary <decisions-path>`, the records with `status: blocked`,
- **alongside the accumulated briefing** — `uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py briefing <decisions-path>` — for context (the auto-taken decisions so far).

Discuss in **prose in the conversation**, dependency-ordered — **NOT** AskUserQuestion. Architectural decisions need back-and-forth. Collect resolutions as structured `overrides` entries (each carrying its blocked decision's `decision_id`, known at collection time). **Also** accept an override of any auto-taken decision the user objects to in that accumulated context — the same `overrides` channel, keyed by decision id. Then re-run.

A `blocked` stop is a **discussion, not an approval opportunity** — do **not** call `approve` / `reject` / `append-non-goal` here. That waits for a `converged` acceptance or a round-cap partial.

### `round-cap`
No convergence within the cap — itself a signal the spec has a structural problem. Present an honest non-convergence report:
- **what kept churning** (from the run and CHANGELOG),
- **which atoms never verified** — `uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py atoms coverage --ledger <atoms-path>` → the `never_verified` list,
- **which decisions are still pending** — `spec_checks.py decisions summary <decisions-path>` → the `status: pending` records,
- accompanied by the **briefing** and **scorecard** (this is an approval opportunity — the invariant holds).

The user then chooses:
- **Re-run** — bare continuation (keep draining the carried dirty set), or carrying `overrides` / `directives` if decisions were discussed. Re-run.
- **Approve the partial work** → `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py approve <target-file-path>` (+ `append-non-goal` per accepted proposal).
- **Reject the partial work** → `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py reject <target-file-path>`.

## Command-side derivation (race-free)

Nothing writes between workflow-exit and command-read (the workflow has exited; only the command runs next). Use exactly these three, all **relative**, in the main session:
- `spec_checks.py briefing <decisions-path>` — the human-facing decision view.
- `spec_checks.py decisions summary <decisions-path>` — structured JSON projection (`id, kind, status, title, confidence, review_first, dropped, radii, depends_on`). Group by `status`: `taken` / `blocked` / `pending` / `proposal`. Exclude any `dropped: true` proposal from the active proposal group (its finding has been un-parked to re-enter the gate).
- `spec_checks.py atoms coverage --ledger <atoms-path>` — emits `{ verified, unverifiable, total, complete, never_verified, dirty }`.

## The scorecard

Shown at every **approval opportunity** (`converged` accept and `round-cap` partial — **NOT** `blocked`). Command-derived, with **mixed scopes explicitly labeled — never silently merged**:

- **This-run (per-invocation)** — from the return: `rounds`, `fixed` (auto-fixable applied, **not** decision-takes), `below_bar`.
- **Session-cumulative (from the sidecars)**:
  - decisions taken / blocked / pending + proposed-non-goal counts — from `decisions summary`,
  - atoms verified / unverifiable / total — from `atoms coverage` (re-render `complete` as `verified + unverifiable == total`),
  - optionally a cumulative `fixed` via a deterministic shell `grep -c` of `[fix]`-kind CHANGELOG entries (**excluding** `[decision-take]` entries — a take is counted under decisions taken, no double-count).

Tag each block with its scope so a last-drain `fixed: N` is never read as a session total.

## Re-run / re-entry rule (load-bearing)

In-session re-runs **re-enter at the Drain-run step (step 7), never Setup.** Before **every** re-invocation:
1. Re-run the read-only `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py paths <target-file-path>` — **never `init`** (whose guard would spuriously re-prompt resume/restart each round) — to freshly derive `next_run` and the current path values.
2. Re-absolutize the path values (step 5's rule).
3. Rebuild the args object with the `overrides` / `directives` collected in this turn (`[]` for a bare continuation).
4. Re-invoke `Workflow(...)`.

Loop until a run exits `converged` and the user accepts the briefing. The Setup `init` guard and its resume/restart prompt are **cold-start only**.

## Args object

Pass the whole `PATHS_JSON` (path values absolutized) as `paths` — the drain reads `paths.source, .auto_improve, .atoms, .decisions, .implementer_notes, .changelog, .non_goals, .history_dir`. Use snake_case keys (the drain tolerates camelCase too, but snake_case matches the concept contract):

```json
{
  "paths": { "...the whole init/paths JSON, path values absolutized against cwd..." },
  "scripts_dir": "<absolutized {MG_INSTALL_SCRIPTS_DIR}>",
  "template_path": "<absolutized {MG_INSTALL_CONCEPT_TEMPLATE}>",
  "scratch_dir": "<absolute SCRATCH_DIR>",
  "run": <next_run from the init/paths JSON>,
  "overrides": [ { "decision_id": "R7", "directive": "free-form override text" } ],
  "directives": [ "free-form editorial instruction tied to no decision record" ]
}
```

- On a **first run**, pass `overrides: []` and `directives: []`.
- `run` = `next_run`, **freshly re-derived from `paths` before every invocation** — a reused run number would overwrite `history/run-N/`, destroying the audit trail.
- `paths.source` (the `<target>` arg) must always be present and absolutized — the drain keys every script on it.

</process>

<important_notes>
- **The command orchestrates; the drain executes one drain run per invocation.** The per-round / per-phase loop discipline lives in the JS, not this file.
- **Only `status` crosses back as a value only the workflow can supply.** `rounds` / `fixed` / `below_bar` are this-run accumulators; **all decision and atom data is derived command-side from the on-disk sidecars via the three `spec_checks.py` calls — never paraphrased** from the return.
- **Auto-taken decisions are never approved unseen.** The briefing accompanies **every** approval opportunity (a `converged` accept and a `round-cap` partial). A `blocked` stop is a discussion, not an approval.
- **All mutation is via `improve_files.py` or the drain's agents — the command holds no Edit/Write.** Working-copy edits, sidecar writes, backup/approve/reject/non-goal appends all go through the script or the drain.
- **The working copy is the safety net.** The original is untouched until `improve_files.py approve`. Fixes and proposed non-goals are approved independently, exactly as `spec-improve` does today.
- **Absolutization rationale.** The Workflow tool's resolution of a *relative* `scriptPath`, and a workflow-spawned agent's cwd, are undocumented. The command is the one context whose cwd is reliably the project root, so it absolutizes every path crossing into the drain (`scriptPath`, `scripts_dir`, `template_path`, all `paths` values) against its own cwd — a no-op on already-absolute `--global`/`--target` forms. Its own `uv run` calls stay relative because they run in the main session. The workflow JS is copied verbatim at install (no sed pass), which is why the command must hand it absolute values.
- **Scratch dir is drain scratch, not a sidecar.** The drain's agents marshal relayed values to files there for scripts (`record-verdicts`, `atoms merge`, `block-gate`). Create it absolute and keep it out of the spec's directory.
</important_notes>
