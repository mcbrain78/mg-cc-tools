# Spec Improve Auto

---
name: mg-temp:spec-improve-auto
description: Autonomous refinement of a concept spec — a main-session loop of fresh-eyes review + fix + deterministic floor, terminated by a substantive exit exam
argument-hint: "<file-path>"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

<objective>
Refine a concept spec autonomously, without a per-round human gate. This command drives a loop **in the main session** (like `mg-temp:spec-improve`, not the Workflow tool): each round spawns a fresh-eyes reviewer, applies the safe fixes, enforces a deterministic structural floor, snapshots for audit, and asks a fresh **exit exam** whether anything substantive is still wrong. It loops until the exit exam comes back clean (converged) or a round cap is hit.

The safety net is unchanged from `spec-improve`: every edit lands on the working copy, the original changes only on explicit `approve`, and fixes and non-goals are approved independently. The user reviews the **result** — a run summary + scorecard — not each round.
</objective>

<context>
Arguments: $ARGUMENTS

Expected: a path to the concept spec to refine (typically `docs/work-queue/todo/{name}/concept.md`).

Concept spec template: `{MG_INSTALL_CONCEPT_TEMPLATE}`

File-operations script: `{MG_INSTALL_SCRIPTS_DIR}/improve_files.py`

Checks script: `{MG_INSTALL_SCRIPTS_DIR}/spec_checks.py`
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
   - **On success (exit 0):** capture the emitted resolved-paths JSON (`source`, `auto_improve`, `non_goals`, `non_goals_exists`, `changelog`, `history_dir`, `next_run`, `original_backup`, `backup_created`, plus the other `*_exists` flags). Store it as `PATHS_JSON`. If `backup_created` is true, report: `Backed up original to <original_backup>`.
   - **On guard-fail (exit 1):** an in-progress working copy from a prior session exists (the D7 guard). Do **not** overwrite it blindly. Run the read-only:
     ```
     uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py paths <target-file-path>
     ```
     to get the resolved-paths JSON, surface the leftover state to the user, then use **AskUserQuestion** for the binary choice:
     - **Resume** — continue with the existing working copy. Use the `paths` JSON as `PATHS_JSON`.
     - **Discard and restart** — run `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py init <target-file-path> --fresh`, then use its JSON as `PATHS_JSON`.

     This AskUserQuestion is the **only** picker before convergence. Everything else in the loop is autonomous.

   From `PATHS_JSON`, bind the paths used throughout:
   - `WORKING` = `auto_improve` (the working copy — every edit lands here)
   - `NON_GOALS` = `non_goals` (may not exist yet; `non_goals_exists` tells you)
   - `CHANGELOG` = `changelog`
   - `RUN` = `next_run` (the run number for this invocation)

**CRITICAL: All modifications happen exclusively on `WORKING`. The original is never touched until the user explicitly approves via `improve_files.py approve`.**

## Path prep for subagents

4. **Get cwd** with a Bash `pwd` (the command runs in the main session, whose cwd is reliably the project root).

5. **Absolutize the paths handed to subagents** — `WORKING`, `NON_GOALS`, `{MG_INSTALL_CONCEPT_TEMPLATE}`, and the project root (`pwd`). Rule: if a path does not begin with `/`, prepend `<cwd>/` (a no-op on already-absolute `--global`/`--target` paths). Subagent cwd is not guaranteed, so reviewer prompts always carry absolute paths. The command's **own** `uv run`, `Read`, and `Edit` calls stay **relative to `WORKING`** — they run in the main session where cwd is known.

## The auto-loop

Run rounds `M = 1, 2, 3, …` up to the **round cap of 20**. Each round is self-contained; carry no reviewer prose between rounds (see **State discipline**). A round:

### 1 — Fresh review (drives fixes)
Spawn ONE reviewer subagent (Agent tool). This is the harsh, wide-net pass — its job is to find everything worth fixing:

```
You are a senior engineer reviewing a file with completely fresh eyes.
You have NO prior context about this project.

Read the file at: {absolute WORKING path}

{If non_goals_exists is true, include:}
Also read the non-goals file at: {absolute NON_GOALS path}
These are explicit scoping decisions — do not flag issues that fall under a
listed non-goal. You may still flag severe bugs in non-goal areas if they
would break something.

Also read the concept spec template at: {absolute template path}
Use it to assess whether expected sections are present and adequately filled.
A thin section is worth flagging if it should have more depth.

If the file references existing functionality — by path, code reference, or
concept ("replaces X", "extends Y") — read that code before reviewing (project
root: {absolute pwd}). You cannot assess a plan without understanding what it
builds on. All issues must be actionable on the target file only.

Provide a critical review focused on:
1. Internal contradictions or inconsistencies
2. Missing pieces that would block implementation
3. Assumptions that aren't stated or validated
4. Overengineering vs underengineering
5. Whether examples actually match the spec text
6. Decision quality — every decision must be real. Open questions
   ("non-blocking", "resolve during implementation"), thin decisions that
   restate a choice without reasoning/tradeoffs/evidence, and deferred
   commitments ("future work", "v2") are NOT decisions — flag them. (Explicit
   scope exclusions like "this plan does NOT cover X" are boundaries, fine.)
7. Simpler alternatives — only if you can name a concrete one and why it's better.
8. Over-specification — flag implementation code (function bodies, algorithms)
   in the spec. A concept defines interfaces/contracts, not bodies. Test: if you
   replaced the code with a prose description, would an implementer still know
   what to build? If yes, the code doesn't belong.
9. Verification coverage — every row in the Scope table needs at least one
   matching item in the Verification section.
10. Citation discipline — in `### What gets built`, every top-level bullet
    (column-0 `- ` line) must cite the design decision(s) it realizes as `(Dx)` /
    `(Dx, Dy)`, referencing `### Dn:` headings. Flag any uncited top-level bullet
    or a citation with no matching D-block.

Be harsh. Flag everything that seems off. Validate claims against code where possible.

Return your findings as a compact list. For EACH issue, one entry in exactly
this shape (no extra prose between entries):

  - [SEVERITY] <section or line> — <what is wrong>. FIX: <suggested fix, or "none">. NEEDS_USER: <yes|no>.

  SEVERITY is critical | major | minor.
  NEEDS_USER is "yes" if resolving the issue requires a human decision, changes
  intent/scope, or is an unresolved architectural choice (a decision-shaped
  finding). Otherwise "no" (a mechanical/clarity fix you could make safely).

If you find nothing worth flagging, return exactly: NO ISSUES.
```

### 2 — Triage + fix
From the reviewer's list, apply this discipline on the working copy:

- **Fix now** every `NEEDS_USER: no` finding you are confident resolves the issue without changing intent or scope — an implementer would otherwise build the wrong thing, get stuck, or have to come back and ask. Read `WORKING`, then `Edit` it. When resolving a "missing piece", specify the interface contract (CLI flags, data shapes, behavior) in prose — **never** write implementation code / function bodies into the spec.
- **Cap: at most 10 fixes this round.** If more than 10 clear the bar, keep the 10 highest-severity; the rest re-surface next round (the reviewer re-derives them — see State discipline).
- **Do NOT touch `NEEDS_USER: yes` (decision-shaped) findings.** This loop takes no decisions. They are left unresolved on purpose; they will re-surface every round and — if never resolved — correctly prevent convergence and be reported at the cap.
- Log each applied fix:
  ```
  uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py append-changelog <target-file-path> --run <RUN> --round <M> --kind fix "<one-line description>"
  ```

### 3 — Deterministic floor
Run the structural + citation floor on the working copy:
```
uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py floor <WORKING>
```
- Exit 0 → floor passes.
- Exit 1 → the emitted `findings` (missing required headings, uncited bullets) are always safe mechanical fixes. Apply them to `WORKING` (respecting the 10-fix budget over the whole round), log each via `append-changelog`, and re-run `floor` until it passes. Floor **must** pass before the round completes.

### 4 — Snapshot (audit trail, not held in context)
```
uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py snapshot <target-file-path> --run <RUN> --round <M>
```
Writes `history/run-<RUN>/round-<M>.md`. Do not read it back — it is an audit artifact, not loop state.

### 5 — Exit exam (drives termination)
Spawn ONE fresh exit-exam subagent (Agent tool). This is a **different, higher bar** than step 1 — it decides *done*, not *nitpick*:

```
You are a senior engineer doing a final readiness check on a concept spec, with
completely fresh eyes and NO prior context.

Read the file at: {absolute WORKING path}
{If non_goals_exists: Also read {absolute NON_GOALS path} — respect those exclusions.}
Concept spec template (for structural expectations): {absolute template path}
If the spec cites code/paths, read them (project root: {absolute pwd}).

Answer ONE question: is anything SUBSTANTIVE still wrong or missing — something
that would make an implementer build the wrong thing, get blocked, or have to
come back and ask? Ignore cosmetic wording, stylistic nitpicks, and anything
already covered by a listed non-goal. Hold a high bar: a spec does not need to
be perfect to be buildable.

An unresolved decision-shaped issue (an open question, a thin/undecided choice,
a deferred commitment that the plan actually needs) IS substantive — report it.

If there is nothing substantive left, return exactly: CLEAN.
Otherwise return a short list, one line each:
  - [SEVERITY] <section> — <what is substantively wrong>. NEEDS_USER: <yes|no>.
```

### 6 — Converge or continue
- **Exit exam returned `CLEAN` AND floor passed this round → CONVERGED.** Stop the loop, go to **On convergence**.
- **Otherwise → next round.** Do not carry the exit exam's findings in context; the next round's fresh reviewer re-derives the live issue set from the (now-updated) working copy on disk.
- **If `M` reaches the cap (20) without converging → STOP at cap.** Go to **On round cap**.

## State discipline (load-bearing)

The orchestrator keeps **nothing durable in its own context**. Every round it re-reads the working copy from disk (to `Edit` it) and spawns fresh, stateless subagents that read from disk themselves. This is what lets one long-running main session survive 10–20 rounds:

- **Never** filter or deprioritize a reviewer's finding using memory of a prior round. Each reviewer's output is the complete, canonical list of live issues. A finding that reappears was not fixed; one that disappears is resolved. The **working copy on disk is the only state** — unresolved issues persist because they are still in (or absent from) the doc.
- If the session is compacted mid-loop, resume by re-deriving position from disk: `M` = (count of `round-*.md` files in `history/run-<RUN>/`) + 1; re-read `RUN`/paths via `improve_files.py paths <target>`; continue the loop. No in-context history is required to proceed.
- After triaging a round, discard the reviewer/exit-exam prose from working memory — do not summarize prior rounds into context. The changelog on disk is the durable record.

## On convergence

Present, in order:
1. **Run summary** — read `<CHANGELOG>` and summarize what changed across the run's rounds (grouped, not verbatim).
2. **Scorecard** — see **The scorecard**.
3. Confirm the exit exam came back `CLEAN` and the floor passes.

Then run the approval flow (fixes and non-goals approved **independently**, exactly as `spec-improve`):
- **Accept** →
  - `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py approve <target-file-path>`
  - for each proposed non-goal the user accepts: `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py append-non-goal <target-file-path> "<non-goal text>"`
  - Acceptance ends the session.
- **Reject** → `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py reject <target-file-path>` (discards the working copy; original untouched).
- The user may instead request specific further changes or another batch of rounds — re-enter the loop from round `M+1` (never re-run Setup; the D7 guard is cold-start only).

## On round cap

Reaching the cap without a clean exit exam is itself a signal — usually an unresolved decision-shaped issue this loop cannot take, or genuine churn. Present an **honest non-convergence report**:
- **What is still blocking** — the last round's exit-exam findings, especially any `NEEDS_USER: yes` (decision-shaped) items the loop left unresolved by design.
- **What kept churning** — summarize from `<CHANGELOG>` (e.g. the same section edited many rounds running).
- **Scorecard**.

Then let the user choose:
- **Re-run** — another batch of rounds from `M+1` (e.g. after the user resolves a blocking decision in discussion and you apply it).
- **Approve the partial work** → `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py approve <target-file-path>` (+ `append-non-goal` per accepted proposal).
- **Reject** → `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py reject <target-file-path>`.

## The scorecard

Shown at every approval opportunity (convergence accept and round-cap partial). Derive it deterministically — do not paraphrase from memory:
- **Rounds run** this invocation = `M`.
- **Fixes applied** = `grep -c '\[fix\]' <CHANGELOG>` (count of logged fix entries; a floor fix is a fix).
- **Outcome** = `converged` or `round-cap`.
- **Still open (if any)** = count of the last round's `NEEDS_USER: yes` exit-exam findings.

</process>

<important_notes>
- **This is a main-session loop, not the Workflow tool.** There is no `.js` drain, no atom ledger, no verification pyramid, no auto-decision block-gate. Those were dropped deliberately for cost and simplicity (see `docs/work-queue/todo/spec-improve-auto/AUTO2-DESIGN.md`). Coverage comes from fresh reviewers over many cheap rounds; termination comes from the exit exam.
- **Two asymmetric fresh looks per round.** The round reviewer (step 1) is deliberately harsh and wide — it drives fixes. The exit exam (step 5) holds a deliberately high, substantive-only bar — it drives termination. This asymmetry is the point: the loop converges when *substantive* issues are gone, even if a harsh reviewer could always find one more cosmetic nitpick. Using the round reviewer's emptiness as the stop signal would risk never terminating.
- **This loop takes no decisions (yet).** Decision-shaped findings (`NEEDS_USER: yes`) are never auto-fixed. If the spec has an unresolved decision, the loop cannot converge on its own — it will run to the cap and surface the decision for the user. Convergence without user interaction therefore requires a spec with no open decisions; a cap-stop that surfaces a real open decision is a correct outcome, not a failure. (Auto-decisions are deferred future work.)
- **Only a subagent reviews with truly fresh eyes.** The main agent carries loop context that biases judgment. Always use the Agent tool for both the reviewer and the exit exam.
- **The working copy is the safety net and the only state.** Every edit lands on `WORKING`; the original is untouched until `approve`. The orchestrator holds no durable round state — it re-reads from disk and is resilient to mid-loop compaction (see State discipline).
- **All file mutation of sidecars/originals goes through `improve_files.py`.** The orchestrator uses `Edit` only on the working copy (to apply fixes); backups, changelog, snapshots, approve/reject, and non-goal appends all go through the script.
- **The 10-fix-per-round cap** bounds blast radius and keeps each round focused, exactly as `spec-improve`. Excess findings re-surface next round.
</important_notes>
