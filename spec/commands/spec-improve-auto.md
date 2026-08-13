# Spec Improve Auto

---
name: mg:spec-improve-auto
description: Autonomous refinement — a main-session loop that reviews, resolves the decisions it can, escalates the ones it can't, and terminates on a substantive exit exam
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
  - CronCreate
  - CronList
  - CronDelete
---

<objective>
Refine a concept spec autonomously, without a per-round human gate. This command drives a loop **in the main session** (like `mg:spec-improve`, not the Workflow tool). Its job is to **drive through decision points**, not just surface them: each round it reviews the spec with fresh eyes, resolves the decisions it can defend, **escalates** only the ones that genuinely need a human, enforces a deterministic structural floor, and asks a fresh **exit exam** whether anything substantive is still wrong. It loops until the exit exam is clean *except for the escalated decisions* (converged) or a round cap is hit.

Because real specs are never decision-complete, a loop that only *surfaces* decisions can never converge. So this command **takes the defensible decisions itself** (researched, written into the spec as resolved design decisions, logged for your review) and reserves your attention for the genuinely hard calls. To keep that affordable, the code a spec cites is read **once** into a shared digest and reused by every agent every round.

The safety net is unchanged from `spec-improve`: every edit lands on the working copy, the original changes only on explicit `approve`, and fixes and non-goals are approved independently. You review the **result** — auto-decisions (to confirm or override) + the escalated decisions (to resolve) — not each round.
</objective>

<context>
Arguments: $ARGUMENTS

Expected: a path to the concept spec to refine (typically `docs/work-queue/todo/{name}/concept.md`).

Concept spec template: `{MG_INSTALL_CONCEPT_TEMPLATE}`

File-operations script: `{MG_INSTALL_SCRIPTS_DIR}/improve_files.py`

Checks script: `{MG_INSTALL_SCRIPTS_DIR}/spec_checks.py`

**Code root:** the spec cites code by relative path (e.g. `compute/foo.py:120`). Those paths resolve against the project the spec belongs to — normally the current working directory (the main session's cwd). Use cwd as the code root unless the spec's code lives in a different checkout.
</context>

<process>

## Setup (cold-start entry only)

1. Parse `$ARGUMENTS` for the target file path plus optional flags `--resume` and `--force` (order-independent; the path is the non-flag argument). If the path is missing:
   ```
   ERROR: File path required.

   Usage: /mg:spec-improve-auto <file-path> [--resume] [--force] [--force-continue]

   Example:
     /mg:spec-improve-auto docs/work-queue/todo/worktrees/concept.md
   ```
   Exit.

   **Flags** (parsed from `$ARGUMENTS`, order-independent):
   - `--resume` — a scheduled or manual resume: at the D7 guard (step 3) auto-**Resume** the existing working copy with no AskUserQuestion. If no working copy exists, fall through to a normal cold start.
   - `--force` — a one-round usage-gate override (implies `--resume`): after binding paths, write an empty `FORCE_MARKER`; the next usage gate (round step 0) consumes it to run exactly one round past the soft limit, then normal gating resumes.
   - `--force-continue` — suppress the stall check (round step 8) for this invocation, so the loop runs to the cap even while the same items keep carrying. The user passes it after a stall report to say they want the remaining rounds anyway. It does not imply `--resume`; combine the flags if both apply.

2. Read the target file. If it doesn't exist or is empty, report the error and exit.

3. **Guarded init.** Run:
   ```
   uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py init <target-file-path>
   ```
   - **On success (exit 0):** capture the emitted resolved-paths JSON. Store it as `PATHS_JSON`. If `backup_created` is true, report: `Backed up original to <original_backup>`. `init` also writes this run's **baseline** — the target exactly as the run found it — to `history/run-<RUN>/baseline.md` (emitted as `baseline`); report it once. Every other file in that dir is a post-edit snapshot, so the baseline is the only in-tree record of where a run started, and it is deliberately not named `round-*.md` (the resume path counts those to derive `M`). `<name>.original.md` does **not** serve this purpose: it is written on the first `init` only and never refreshed, so it is run 1's baseline forever.
   - **On guard-fail (exit 1):** an in-progress working copy from a prior session exists (the D7 guard). Do **not** overwrite it. **If `--resume` or `--force` is set** (a scheduled or manual resume), auto-**Resume**: run the read-only `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py paths <target-file-path>`, use its JSON as `PATHS_JSON`, and skip the question. **Otherwise** run `paths`, surface the leftover state, and use **AskUserQuestion** for the binary choice:
     - **Resume** — continue with the existing working copy. Use the `paths` JSON as `PATHS_JSON`.
     - **Discard and restart** — run `improve_files.py init <target-file-path> --fresh` (then `improve_files.py scratch-clean <target-file-path>` to clear any stale scratch), and use the init JSON.

     This AskUserQuestion is the **only** picker before convergence (a `--resume`/`--force` invocation skips even this). The loop is otherwise autonomous.

   Bind from `PATHS_JSON`:
   - `WORKING` = `auto_improve` (every edit lands here)
   - `NON_GOALS` = `non_goals` (may not exist yet; `non_goals_exists` tells you)
   - `CHANGELOG` = `changelog`
   - `RUN` = `current_run` — the resume-aware run number. **Not `next_run`**: that is cold-start-only (highest history run + 1), so once the in-progress run has snapshotted a round it over-counts by one; on a `--resume`, binding `next_run` would fork the round into a phantom `run-<N+1>` and break the eventual `approve`. `current_run` is the run that owns the live working copy (a `.spec-run` marker written by `init`; inferred from the latest un-sealed history dir if the marker is absent).
   - `HISTORY` = `history_dir`

   Also define, siblings of `WORKING` (derive by string, do not create yet):
   - `DIGEST` = `<dir-of-WORKING>/CODE-DIGEST.md` — the shared code facts (Step 0)
   - `FORCE_MARKER` = `<dir-of-WORKING>/.usage-force` — the one-round usage-gate override token. **If `--force` was passed, write this file now** (empty); the first usage gate consumes it.
   - The escalation store is **in-document**: a loop-owned `## Open Decisions` section inside `WORKING` (see **Escalations**), not a sidecar.

**CRITICAL: All modifications happen exclusively on `WORKING`. The original is never touched until the user explicitly approves via `improve_files.py approve`.**

## Path prep for subagents

4. **Get cwd** with a Bash `pwd`. Set `CODE_ROOT` = cwd (see Context).

5. **Absolutize the paths handed to subagents** — `WORKING`, `NON_GOALS`, `DIGEST`, the **target file** (as `TARGET_ABS`, for the applier's `append-changelog` calls), `{MG_INSTALL_CONCEPT_TEMPLATE}`, `CODE_ROOT`. Rule: if a path does not begin with `/`, prepend `<cwd>/`. Subagent cwd is not guaranteed, so every path in an agent prompt is absolute (the per-round `SCRATCH` path is already absolute — `scratch-dir` prints it resolved). The command's own `uv run` calls stay relative to `WORKING`.

## Step 0 — Code digest (once per run; the "read once")

6. If `DIGEST` does **not** exist, spawn ONE **digest-reader** subagent on the **Sonnet** model (mechanical, read-heavy extraction). Prompt:

```
You are building a factual reference digest of a codebase for other agents to
rely on. Read ONLY; write exactly one file.

A concept spec at {absolute WORKING path} cites source code by relative path
(e.g. `compute/foo.py:120`, `bar.py`, function/class names). Those paths resolve
under the project root: {absolute CODE_ROOT}.

1. Extract every code reference the spec makes (paths, files, functions, classes,
   config keys, line refs).
2. Read that code (and immediately-adjacent code needed to state a fact
   correctly — signatures, call sites, what a function actually does).
3. Write a compact digest to: {absolute DIGEST path}

The digest is the ground truth other agents will use to check the spec's claims
WITHOUT re-reading the codebase. For each cited entity record, tersely: its real
signature / shape; what it actually does (esp. where the spec makes a behavioral
claim — e.g. "fetches limit=8, not 165"); and any fact that confirms or
contradicts the spec. Group by file. Facts only — no spec critique. Note any
citation you could not resolve (missing file / wrong line). Keep it as short as
fidelity allows.

DECLARE YOUR OWN GAPS. Other agents treat this file as ground truth, so a hole in
it reads to them as a fact about the code. End the digest with a `## Not deep-read`
section naming every cited file you did NOT read in full — one line each with the
reason (too large, skimmed, resolved by name only). A file you read partially
belongs in that list even though its citation resolved: "resolved" and "read" are
different claims. If the list would be empty, write `## Not deep-read` then `none`.

Return one line: the digest path + entity count + the not-deep-read file count.
```

   If `DIGEST` already exists (a re-run, or a resumed session), **reuse it** — code is static across a refinement run. (Only refresh if the user says the code changed: delete `DIGEST` and re-run Step 0.)

   **The digest is evidence of presence, never of absence.** It is a partial read by construction — which is why it must declare its own gaps — so its silence on a symbol is a fact about the digest, not about the code. No agent may conclude that a cited function, column, table or file does not exist because the digest omits it; that claim requires opening the file under `CODE_ROOT`, and a cited file listed under `## Not deep-read` must be opened rather than trusted. This rule is not theoretical: a round once deleted a real function from a spec as a "mechanical fix" on the strength of digest silence, replacing it with a similarly-named function that reads a different table, and the three rounds after it carried the wrong citation. Every agent prompt below restates the rule.

## The auto-loop

Rounds `M = 1, 2, 3, …` up to the **round cap of 20**. Each round is self-contained (see **State discipline**).

**The orchestrator is a thin router — it never reads or edits `WORKING` itself.** Each round it spawns subagents, hands them **absolute file paths**, and gets back only **one-line summaries** (ids, counts, a verdict word). All bulky content — the spec text, the findings, the proposed edits — flows agent → disk → agent through a per-round scratch dir and never enters the main context; that is what keeps context flat across a long run. At the **start of every round**, resolve (and create) that dir, capturing the absolute path it prints:
`uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py scratch-dir <target> --run <RUN> --round <M>` → store as `SCRATCH`.
Hand `<SCRATCH>/handoff-review.md`, `<SCRATCH>/handoff-decide-<cluster>.md`, and `<SCRATCH>/handoff-exit.md` to the agents below. (These handoff files use neutral `handoff-*` names **deliberately**: a subagent `Write` to a `findings`/`report`-named file trips a Claude Code behavioral guard that pushes report output back into the response — which would break the round. The neutral name both sidesteps that guard and describes the file accurately as inter-agent handoff state, not a report. Do **not** rename them to `findings.md`/`report.md`.)

Also derive, by string, the run's **exit-carry file** — `EXIT_CARRY` = `<parent-of-SCRATCH>/exit-carry.md`, i.e. `.spec-scratch/run-<RUN>/exit-carry.md`. It is per-RUN, not per-round: the exit exam rewrites it every round and the next round's reviewer reads it, so a substantive item the exit exam names is **routed to a resolver instead of resampled**. Without it the exit exam is write-only — it holds the loop's highest bar and the widest evidence base (it may open code), and every item it finds is discarded at the end of the round, so the loop's own termination signal measures nothing but what one agent chose to list. Sitting at the run root, it is removed by the existing `scratch-clean` at a terminal state and needs no new subcommand. A round:

### 0 — Usage-limit gate (before any work this round)
Run: `uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py usage-gate --session-max 75 --weekly-max 90`. It reads Claude Code's real `/usage` (cost-free) and returns JSON: `verdict` (`OK` | `PAUSE` | `ERROR`), `session_pct`, `weekly_pct`, `binding` (`session` | `weekly` | null), `resume_cron`, `resume_human`.
- **If `FORCE_MARKER` exists** → delete it and proceed to step 1 regardless of the verdict — the one-round override; note "usage gate overridden — one round" in the run output, and the next round gates normally.
- **`OK`** → proceed to step 1.
- **`ERROR`** (could not read `/usage`) → proceed to step 1; a monitoring hiccup must not halt the loop.
- **`PAUSE`** → do NOT run the round; go to **On usage pause**.

### 1 — Fresh review (Sonnet — drives fixes + finds decisions)
Spawn ONE reviewer subagent on the **Sonnet** model. It reads the spec + the digest (not the whole codebase), and is the harsh, wide-net pass:

```
You are a senior engineer reviewing a concept spec with completely fresh eyes.
You have NO prior context.

Read the spec at: {absolute WORKING path}
Read the code-facts digest at: {absolute DIGEST path} — use it as ground truth
about the cited code instead of re-reading the codebase. Only open a specific
source file (under {absolute CODE_ROOT}) if the digest is silent on a fact you
need. THE DIGEST IS EVIDENCE OF PRESENCE, NEVER OF ABSENCE: it is a partial read
and declares its own gaps under `## Not deep-read`. Never conclude that a cited
function, column, table or file does not exist because the digest omits it — open
the file and look. A cited file named under `## Not deep-read` must be opened
rather than trusted.
{If non_goals_exists: Also read {absolute NON_GOALS path}. A listed non-goal's
SCOPE is exempt — do not flag work it excludes. But its RATIONALE is NOT: if a
non-goal's stated justification rests on a false or unvalidated premise, flag that
(a foundational premise often hides inside a non-goal). Severe bugs excepted.}
Also read the concept spec template at: {absolute template path} — assess whether
expected sections are present and adequately filled.

{If M > 1 and EXIT_CARRY exists: Read the previous round's unresolved substantive
items at {absolute EXIT_CARRY path}. The exit exam named them at a higher,
substantive-only bar than yours, with permission to open code, and nothing has
resolved them yet. They are a SEED LIST you must account for, not background
reading. For EACH item do exactly one of:
  - re-raise it as one of your own findings with `Touches` filled in, so it reaches
    a resolver this round — the normal case, since an item is on that list
    precisely because nothing has fixed it; or
  - record it as gone: a finding with `Decision: no`, `Fix: none`, and a Problem
    reading `CARRIED ITEM RESOLVED: <the item> — <what in the spec now answers it>`.
Silently dropping a carried item is the single failure this list exists to prevent.
A re-raised item is still subject to the `## Open Decisions` skip rule below.}

IGNORE anything already listed under a `## Open Decisions` heading in the spec —
those are known, already escalated to the user; do not re-flag them. Also skip
any spec section named in an Open Decision's **Governs** line: it is under an
open call and must not be re-flagged until that call is resolved.

Provide a critical review focused on: (1) internal contradictions; (2) missing
pieces that block implementation; (3) unstated/unvalidated assumptions; (4) over/
under-engineering; (5) examples that don't match the text; (6) decision quality —
open questions, thin decisions (a choice with no reasoning/tradeoffs/evidence),
and deferred commitments ("future work", "later phase") are NOT real decisions,
flag them (explicit scope exclusions are fine); (7) a concrete simpler
alternative, if you can name one and say why; (8) over-specification — flag
implementation code (function bodies/algorithms); a concept defines contracts,
not bodies. Also flag NUMERIC over-specification, per MEASUREMENTS below;
(9) verification coverage — every `### What gets built` bullet needs
a matching Verification item; (10) citation discipline — every top-level bullet
in `### What gets built` must cite `(Dx)` referencing a real `### Dn:` block;
(11) FOUNDATIONS — name the design's few load-bearing architectural premises (the
cross-cutting commitments/invariants implied by the decisions AND the non-goals) and
flag any that is unvalidated, contradicts the digest, is applied inconsistently
across decisions, or would FLIP the design if a fact only the user holds turned out
different (a cost / scale / vendor-limit / operational assumption). Do NOT try to
validate every small assumption — surface the SPINE.

MEASUREMENTS vs DESIGN PARAMETERS — governs criteria (1), (5) and (8). Every number
in the spec is one of two things, and they are reviewed differently:
  - A DESIGN PARAMETER is a value the spec CHOOSES — a threshold, window, limit,
    retry count, or the input set the work is defined over. It IS functionality:
    change it and what gets built changes. Exactness and cross-document consistency
    are load-bearing. Two design parameters that disagree is a critical internal
    contradiction under (1); one that contradicts the digest is a critical finding.
    Nothing below softens this.
  - A MEASUREMENT is a value the spec OBSERVED about the world or the data at some
    past moment — a count, a census, a row total, a share of a population. It is
    EVIDENCE FOR a decision, not the decision. Only its MAGNITUDE relative to the
    threshold that drove that decision is load-bearing ("most", "a clear majority",
    "a small minority") — never its exact digits. You cannot re-derive one: the
    digest is code facts, and a measurement comes from data. Therefore:
      * Do NOT flag drift between two restatements of a measurement as an internal
        contradiction, and never ask for one to be recomputed, re-run or bounded.
      * DO flag it ONCE under (8) — a measurement restated in more than one place,
        or stated to a precision the decision it grounds does not need. Emit ONE
        finding for that measurement, never one per disagreeing site, with
        `Decision: no` and `Fix:` = state it once at the magnitude the decision
        needs, with its provenance (what it was measured over, and roughly when),
        and delete the restatements.
      * ONE case is a real finding: the decision a measurement grounds would FLIP
        at a plausible different value AND the spec does not record what the
        measurement was taken over. That is an unvalidated assumption — (3),
        `Decision: yes` — and it is a question for the user, not a number to go
        recompute.

Be harsh. Validate claims against the digest.

WRITE your findings to {absolute SCRATCH/handoff-review.md path} — one block per finding:
  ## <id> — [SEVERITY] <section/line>
  Problem: <what is wrong>
  Fix: <suggested fix, or "none">
  Decision: <yes|no>
  NeedsUser: <yes|no>
  Conflict: <yes|no>
  Touches: <comma-separated list, or "none">
  (<id> = F1, F2, …; SEVERITY = critical | major | minor.
   Decision = yes if resolving it is a design decision — a choice among
     alternatives, a premise to correct, an open question/deferral to close;
     no if it is a mechanical/clarity fix. ALWAYS yes if the fix would delete,
     rename or re-point a code citation, or rests on a cited symbol not existing:
     that is a factual claim about the codebase, not a wording change, and it must
     reach an agent allowed to open the file. A "mechanical" citation edit applied
     on digest silence is exactly how a real function gets deleted from a spec.
   NeedsUser = yes only if the decision genuinely needs a human — changes intent/
     scope, high-stakes, or you cannot determine the right answer even from the code.
   Conflict = yes if the finding is that two things in the spec DISAGREE — two
     decisions, a decision and an example, a rule and the fixture that tests it.
     A Conflict finding MUST name every disagreeing party in Touches.
   Touches = every `Dn` / `ODn` block and named section a fix would have to EDIT —
     not merely mention. Be complete: this is what routes findings that share a
     target to one resolver instead of several blind ones.)

Then GROUP the `Decision: yes` findings into clusters: two findings whose Touches
sets share ANY entry go in the same cluster, and that grouping is transitive (F1
touching D3 and F2 touching D3,D9 and F5 touching D9 are ONE cluster). A finding
touching nothing another touches is its own cluster of one. Number them C1, C2, ….

Then RETURN ONLY this compact index — no prose, no finding bodies:
  FINDINGS: {absolute SCRATCH/handoff-review.md path}
  MECH: <count of Decision:no findings>
  CLUSTERS:
    C<k>: <finding ids, comma-separated> — <union of their Touches>[ NEEDS_USER][ CONFLICT]
    (one line per cluster; NEEDS_USER if any member has NeedsUser: yes,
     CONFLICT if any member has Conflict: yes)
  DECISIONS:
    <id> — <≤8-word gist>   (one line per Decision:yes finding, any order)
If nothing worth flagging: write handoff-review.md with just a heading and return exactly NO ISSUES.
```

### 2 — Drive the decisions (Opus — one agent per CLUSTER, take or escalate; propose only)
For each `C<k>` line in the reviewer's CLUSTERS index (there is no need to read `handoff-review.md` yourself — pass the cluster's finding ids along), spawn a **decide** subagent on the **Opus** model. Spawn them **in parallel** (in one message): each only reads and writes its own file, so there is no contention. A wrong take gets written into the spec, so this stays Opus. Each decide-agent reads its cluster's findings from `handoff-review.md`, may open a specific source file under `CODE_ROOT` if the digest is thin, and **writes its result to disk — it never edits the spec** (a single applier is the sole writer).

**One agent per cluster, not per finding, is the point.** Findings that touch the same decisions are the ones whose fixes can contradict each other, so they are resolved together by one agent that sees every block involved. Findings that touch nothing in common are already independent and still fan out.

**Close the write window before you spawn them.** Run `chmod 444 <absolute WORKING path>` FIRST, in the same step, every round. The decide-agents hold `Edit`, and the prompt telling them not to use it on `WORKING` is not a control — measured: four decide-agents edited one 8,500-line spec concurrently in a single round, in a loop whose prompt states the propose-only rule twice. A read-only file turns that from a silent success into an `EACCES` the agent recovers from by writing its handoff file, which is what it was asked to do. Step 3 reopens the window for the applier.

```
You are resolving ONE CLUSTER of related findings in a concept spec — findings that
touch the same decisions, so they must be resolved as a SET, by you, together. Fresh
eyes, no prior context. You only PROPOSE — you do NOT edit the spec (a single applier
writes it).
Spec (read-only): {absolute WORKING path}   Code-facts digest: {absolute DIGEST path}
Findings: {absolute SCRATCH/handoff-review.md path} — resolve findings "{ids}".
They touch: {the cluster's Touches union}. READ EVERY ONE of those blocks in full
before you decide anything: a resolution that contradicts a decision you did not
read is this loop's most expensive failure mode.
(open a specific file under {absolute CODE_ROOT} only if the digest lacks a fact
you need). {If non_goals_exists: Non-goals: {absolute NON_GOALS path}.}
THE DIGEST IS EVIDENCE OF PRESENCE, NEVER OF ABSENCE — it is a partial read and
declares its gaps under `## Not deep-read`. If your resolution turns on a cited
symbol not existing, or on which of two similarly-named functions a claim is about,
OPEN THE FILE. Do not resolve that from digest silence.

Research the cluster against the digest/code, then WRITE your result to
{absolute SCRATCH/handoff-decide-{cluster}.md}. The file holds one or more RESULT
blocks separated by a line containing only `---`. Emit one block per finding —
EXCEPT where several findings are one underlying problem: then emit a SINGLE block
resolving them together, listing every id it covers. Prefer the joint block.

TAKE — if there is a clearly defensible answer, it does NOT reverse a stated
non-goal or the spec's evident intent, and you can enumerate everything it changes:
  RESULT: <finding ids this block resolves>
  ACTION: take
  CHANGELOG: <one line: what was decided>
  EDIT:
  <the exact new/replacement spec text AND where it goes — a repaired or new
   decision block (Choice / Why / Alternatives rejected, per the template), a
   corrected premise, a resolved open item. Contracts/prose, never implementation
   code. Name the anchor precisely (e.g. 'replace the paragraph starting "…"' or
   'append as a new decision under ## Design Decisions'). Write it FUNCTIONALLY —
   accuracy over polish; the briefing writer polishes later.>
  IMPACT:
  - <anchor> — <what it says now> -> <what it must say>
  <one line per OTHER place in the spec that restates the fact this EDIT changes.
   Before writing IMPACT, SEARCH the working copy for every number, count, step
   label, condition letter, table/column name and decision id your change alters,
   and list EVERY hit that would go stale. Write "none" only if you searched and
   there were none. The applier applies EDIT + IMPACT as ONE change — an incomplete
   IMPACT list is exactly how this round's fix becomes next round's contradiction.>

ESCALATE — if the answer is genuinely ambiguous, high-stakes, or would reverse
intent/a non-goal. This INCLUDES a FOUNDATIONAL premise where a fact only the user
holds (a product / operational / cost / scale / vendor-limit assumption you cannot
verify from code) would FLIP the design if it differs — frame the real alternatives
as options and let the user decide; never guess the fact. (Functional notes are
fine — the briefing writer polishes the prose later; just be accurate and complete):
  RESULT: <finding ids this block resolves>
  ACTION: escalate
  TITLE: <short title>
  SITUATION: <the relevant state of the world, 1-2 sentences>
  PROBLEM: <the tension that forces a choice, and why you cannot just take it
           (genuinely ambiguous / high-stakes / would reverse intent)>
  OPTIONS:
  - a — <tradeoff (pros/cons)>
  - b — <tradeoff>
  - c — <tradeoff>
  (the REAL options — usually 2-4; do NOT pad to a fixed count. The lowercase
   letters are what the user types back.)
  RECOMMENDATION: <your lean named by its letter (e.g. "b") + confidence, and the
                  one reason it wins>
  GOVERNS: <the spec sections/decisions this choice controls, so review skips them
           until it is resolved — e.g. "the WASO solution section, D1, D8, D10">

TWO THINGS IN THE SPEC DISAGREE (a `Conflict: yes` finding) — resolve which kind it
is before you choose an action, because the two kinds route differently:
  - A DRAFTING inconsistency: both statements were meant to say the same thing and
    one went stale — a number, a step label, a condition letter, a count, a rule
    restated in a second place and only updated in the first. There is no design
    question here. TAKE it: state the fact once, authoritatively, and put every
    other site in IMPACT. Do not escalate a stale quotation.
  - A DESIGN FORK: the two statements encode genuinely different intents, and
    picking either changes what gets built. ESCALATE it as one item covering the
    whole conflict — never silently pick a side, and never resolve half of it.
You cannot leave a conflict in place: every finding in your cluster ends in a TAKE
or an ESCALATE block.

NEVER ALLOCATE AN IDENTIFIER. Where your edit adds a new decision block, open item,
build-order step or numbered condition, write the placeholder `<NEW-D>`,
`<NEW-OPEN-ITEM>`, `<NEW-STEP>` or `<NEW-CONDITION>` where the number goes — and use
the same placeholder in every reference to it within your own blocks. Parallel agents
all read the same highest existing number, so any number you pick collides with
another agent's. The applier is the sole writer and the sole allocator.

Default to TAKE when you can defend it; escalate only what truly needs the human.
RETURN ONLY one line per RESULT block:
  {ids} take — <≤10-word gist>   OR   {ids} escalate — <≤10-word gist>
```

Each decide-agent returns one line per RESULT block; the orchestrator holds only those lines. The edit text, the impact lists and the escalation beats stay in the `handoff-decide-<cluster>.md` files for the applier.

### 3 — Apply the round (Sonnet — the sole writer; transcribes, does not judge)
**Reopen the write window first:** run `chmod 644 <absolute WORKING path>` before spawning, unconditionally and every round — including rounds where step 2 spawned no agents at all, so a window left closed by an aborted round is repaired here rather than inherited. The applier cannot write a 444 file, and this is the step where "sole writer" stops being a convention and becomes the only process holding the permission.

Spawn ONE **applier** subagent on the **Sonnet** model. It is the *only* thing that writes `WORKING` this round: it transcribes the already-decided changes (the judgment happened in Steps 1–2), so it exercises no judgment — a mis-placed edit is self-correcting (the next reviewer re-flags it) and the edit *text* is authored verbatim by the Opus decide-agents. It **always runs** (it also owns the deterministic floor), even when there is nothing to apply:

```
You are the applier: the SOLE writer of a concept spec this round. You TRANSCRIBE
already-decided changes; you do NOT re-judge them.
Spec (edit in place): {absolute WORKING path}
Findings: {absolute SCRATCH/handoff-review.md path}
Decisions: every {absolute SCRATCH}/handoff-decide-*.md file (there may be none).
Each holds one or more RESULT blocks separated by a line containing only `---`.

Budget: apply at most 10 changes TOTAL (mechanical fixes + TAKE blocks), highest
severity first (a TAKE's severity is that of its originating finding in handoff-review.md,
matched by the ids on its RESULT line); leave the rest — they re-surface next round.
**A TAKE's EDIT plus its whole IMPACT list is ONE change**, however many sites it
touches — the point of the budget is to bound judgment, and the impact sites carry
none: they are the same fact restated. Applying an EDIT without its IMPACT is never
the cheaper option; it is how a fix becomes next round's contradiction. Escalations
do NOT count against the budget.

1. MECHANICAL FIXES — for each finding in handoff-review.md with `Decision: no`, apply its
   `Fix` (prose/contract only, NEVER implementation code). A "missing piece" that
   needs a design choice is a decision, not a fix — skip it here. REFUSE one shape:
   a `Decision: no` fix that DELETES, RENAMES or RE-POINTS a code citation, or rests
   on a cited symbol not existing. Skip it and report it — it was misclassified and
   belongs with a decide-agent that can open the file. Digest silence is not evidence
   of absence, and you are not the agent that checks. A finding whose Problem begins
   `CARRIED ITEM RESOLVED:` needs no edit at all — it is a bookkeeping note from the
   reviewer; do not count it against the budget and do not log it.
2. TAKE — for each RESULT block with `ACTION: take`, apply its `EDIT` VERBATIM at the
   location it names, then apply every line of its `IMPACT` list. Do NOT reword the
   edit text. If an IMPACT line's target no longer says what the line quotes, apply
   the rest and report that one line as a skip — never guess a replacement.
3. ESCALATE — for each with `ACTION: escalate`, append an `### ODn — <TITLE>` entry to
   the `## Open Decisions` section (create it once, near the end, before
   `## Verification` if present, else at end) from the fields: **Situation**,
   **Problem**, lettered **Options** (keep the a/b/c letters exactly) with tradeoffs,
   **Recommendation**, then a closing `Governs (skip in review until resolved): <GOVERNS>`
   line. Keep it functional.
4. ALLOCATE — you are the round's SOLE allocator of identifiers, because you are its
   sole writer. Proposals arrive with `<NEW-D>`, `<NEW-OPEN-ITEM>`, `<NEW-STEP>`,
   `<NEW-CONDITION>` placeholders and the `ODn` numbers above. For EACH numbered list
   the round writes into — the `### Dn:` decisions, `## Open Decisions`, any
   `## Open Items` or build-order or lettered-condition list the spec already keeps —
   read its current highest number ONCE, then hand out the next values in order across
   ALL proposals, so two proposals adding to the same list can never receive the same
   number. Replace every placeholder, including the references to it inside the same
   proposal. If a proposal arrives carrying a hard-coded number for something it is
   ADDING, treat that number as a placeholder and re-allocate it.
5. If an edit does NOT apply cleanly (anchor missing / conflict), SKIP it and report
   it — never improvise. If two TAKE blocks edit the same anchor with incompatible
   text, apply NEITHER and report both — a contradiction applied is worse than a
   change deferred, and the next round re-derives it with both in view.
6. FLOOR — run `uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py floor {absolute WORKING path}`;
   its findings (missing required headings, uncited bullets) are safe mechanical
   fixes — apply and re-run until it exits 0.
7. LOG — one call per applied change:
   `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py append-changelog {TARGET_ABS} --run {RUN} --round {M} --kind fix|decision-take "<one line>"`
   (use the decide-agent's CHANGELOG line for takes; the finding's Problem for fixes).
   A take's entry names the identifiers you allocated, never the placeholders.

RETURN ONLY:
  APPLIED fixes=<a> takes=<b> impact-sites=<i> escalations=<c> skipped=<s>
  (if s>0, one extra line per skip:  SKIP <id> — <why>)
```

### 4 — Periodic reconcile (Opus — every 3rd round only)
**Run this step only when `M` is a multiple of 3** (rounds 3, 6, 9, …); otherwise go straight to step 5.

Every round appends: a take adds a decision block, a fix adds a qualifying sentence, an escalation adds a memo. Nothing ever removes the text that stopped describing the document three rounds ago, so the doc grows monotonically and each stale span is one more thing a later decision can be read as contradicting. This step is the only downward pressure in the loop.

Spawn ONE **reconcile** subagent on the **Opus** model, handing it the agent instructions at `{MG_INSTALL_RECONCILE_AGENT}`, the absolute `WORKING` path, and **`MODE: cleanup-only`**. It strips draft-history narrative ("reversed from the as-drafted rule", "changed this round"), fixes stale range/count references, and trims `Context:` preambles that merely restate the Problem — presentation only, never design content.

`cleanup-only` is not a lesser setting; it is the correct one mid-loop. It **skips renumbering**, which the finalize pass does. Every `[decision-take]` line already in `CHANGELOG`, and every `Governs` line the reviewer uses as its skip-list, names decisions by number; renumbering between rounds would silently re-point all of them.

Then confirm the cleanup left no broken reference behind — read back a single number, not the report:
```
uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py reconcile-audit {absolute WORKING path} \
  | python3 -c "import json,sys; print(len(json.load(sys.stdin)['dangling_references']))"
```
`0` → proceed to step 5. Anything else → re-spawn the reconcile agent naming what dangles, and re-check. Do **not** act on the numbering gaps this command also reports: mid-loop they are expected, and closing them is finalize's job.

### 5 — Snapshot
`uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py snapshot <target> --run <RUN> --round <M>` (writes `history/run-<RUN>/round-<M>.md`; do not read it back). This is the round's resume anchor; the floor already passed inside the applier, and on a reconcile round the snapshot captures the cleaned copy.

### 6 — Exit exam (Opus — drives termination)
Spawn ONE exit-exam subagent on the **Opus** model — a higher, substantive-only bar than the step-1 review:

```
You are doing a final readiness check on a concept spec. Fresh eyes, no context.
Spec: {absolute WORKING path}   Code-facts digest: {absolute DIGEST path}
(open a file under {absolute CODE_ROOT} only if a substantive judgment needs it).
{If non_goals_exists: Non-goals: {absolute NON_GOALS path}.}

Is anything SUBSTANTIVE still wrong or missing — something that would make an
implementer build the wrong thing, get blocked, or have to come back and ask?
Ignore cosmetic nitpicks, and work a listed non-goal excludes (its scope) — but a
non-goal's RATIONALE is in scope: a non-goal resting on a false/unvalidated premise
IS substantive. Also substantive: a foundational premise applied inconsistently, or
two design decisions that disagree.

NOT substantive: an imprecise, slightly stale, or inconsistently restated
MEASUREMENT — a count, census, row total or population share the spec OBSERVED
about the data at some past moment, as opposed to a DESIGN PARAMETER the spec
CHOOSES (a threshold, window, limit, or the input set the work is defined over).
A measurement is evidence for a decision; only its magnitude relative to the
threshold that drove that decision is load-bearing. You cannot re-derive one — the
digest is code facts and a measurement comes from data — so NEVER list one as an
item to go recompute, re-run or bound; an item nothing in this loop can resolve
carries forever and reads as a stall. A DESIGN PARAMETER that is wrong, or that two
sections state differently, remains fully substantive. The one substantive case for
a measurement is a DECISION, not a number: the decision it grounds would FLIP at a
plausible different value AND the spec does not record what it was measured over.
List that with `DECISION: yes`.

Do NOT count anything already listed under the spec's `## Open Decisions` heading,
or any spec section named in an Open Decision's **Governs** line — those are known
and deliberately escalated to the user; treat them as resolved for the purposes of
this check.

{If EXIT_CARRY exists: FIRST read your own previous verdict at {absolute EXIT_CARRY
path} — the items the last exit exam left open. Re-check each one against the spec
as it now stands: it is CARRIED if it is still true, and closed if the spec now
answers it. Then look for what is NEW. You are not bound by that list — a carried
item you judge closed is closed — but you must decide each one deliberately rather
than by not noticing it.}

Your list is the loop's termination signal, so its LENGTH must mean something. List
EVERY substantive item you find, most severe first, up to 12; do not stop at a
comfortable number. If you hit 12 with more to say, say so — a truncated list read
as a falling count is how this loop convinces itself it is converging.

ALWAYS WRITE {absolute EXIT_CARRY path}, even when clean (empty file), and write the
same list to {absolute SCRATCH/handoff-exit.md path}. One line per item:
`- [SEVERITY] [CARRIED|NEW] <section> — <what is substantively wrong>. DECISION: <yes|no>.`
Anchor each item on quoted spec text or a code path, NOT on a decision number —
decisions get renumbered, so a `Dn` reference goes stale between rounds.

If nothing substantive remains (outside `## Open Decisions`), return exactly: CLEAN
Otherwise RETURN ONLY: DIRTY <n> CARRIED <k> TRUNCATED <yes|no>
  (n = substantive items listed; k = how many of them are CARRIED; TRUNCATED yes if
   you had more than 12.)
```

### 7 — Record the verdict
Log the round's result so the loop can read its own trend off disk instead of your memory:
```
uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py append-changelog {TARGET_ABS} \
  --run {RUN} --round {M} --kind exit "<CLEAN, or the whole DIRTY n CARRIED k TRUNCATED x line>"
```
Log the verdict line **verbatim**, `CARRIED` and `TRUNCATED` included — the stall check reads `CARRIED`, and a bare count is what made an earlier version of this loop stop on the wrong signal. `exit` entries are not applied changes and do not enter the scorecard's fix/take counts.

### 8 — Converge, stall, or continue
Branch on the exit-exam's one-line verdict alone — you hold no round content:
- **`CLEAN` (and the floor passed — the applier drove it to 0) → CONVERGED.** Go to **On convergence**.
- **`M` reaches 20 without converging → STOP at cap.** Go to **On round cap**.
- **`DIRTY …` → check the trend, then continue.** From `M >= 4`, and unless `--force-continue` was passed, read the series with
  `grep '\[exit\]' <CHANGELOG> | tail -3`. **STOP: stalled** only if all three lines carry `CARRIED 2` or higher — the same two-or-more items have now survived three consecutive rounds *after* being routed to a resolver. Go to **On stall**. Otherwise carry nothing in context; the next round's fresh agents re-derive from the updated `WORKING` + the digest and the carry file. Increment `M`.

  **Stall on identity, not on the count.** A count that holds steady is the normal shape of a large spec: each round the exit exam samples the most substantive things it can see, closes some, and reaches items the previous pass had no room for, so `4 → 6 → 5 → 5` can be four rounds of real progress over eighteen different items. What is NOT progress is the same item surviving round after round having been handed to a resolver — that means the loop cannot resolve it, and more rounds of the same shape will not. `CARRIED` measures exactly that; the count measures the exit exam's output discipline. Report both at the stall, and never present the count as the reason.

  Note the interaction with the carry file: `CARRIED` is only meaningful because step 1 routes every carried item to a resolver. If that routing is removed, this check degrades into the count check it replaced.

## State discipline (load-bearing)

The orchestrator keeps **nothing durable in its own context** — and, in the flat-context loop, almost nothing *transient* either:
- **The orchestrator never reads or edits `WORKING`.** Every round it only spawns agents with paths and reads back one-line summaries. All spec text, findings, and proposed edits live in files (the per-round `SCRATCH` dir and `WORKING`), read and written by subagents whose context is discarded on return. This is what holds the main context flat over a 20-round run.
- **`WORKING` on disk is the state.** Unresolved issues persist because they are still in the doc; the reviewer re-derives the canonical live list each round. Never filter a finding using memory of a prior round.
- **`## Open Decisions` in `WORKING` is the escalation memory** — an escalated decision lives there, so future reviewers skip it and it is not re-researched (the same mechanism as `NON_GOALS`). It is the durable cross-round record of what the USER owes an answer on, and it lives in the doc, not your context.
- **`EXIT_CARRY` (`.spec-scratch/run-<RUN>/exit-carry.md`) is the cross-round record of what the LOOP still owes** — the exit exam's unresolved items, rewritten every round and read by the next round's reviewer, which must route or explicitly close each one. It is the counterpart to `## Open Decisions`: one carries the human's queue, the other the loop's. Unlike the per-round handoffs it is genuinely cross-round state, so it lives at the run root rather than inside a round dir; it is still ephemeral in the sense that matters (regenerated every round, removed by `scratch-clean` at a terminal state, and a missing one just means the round runs unseeded).
- **`DIGEST` is computed once and reused** every round and across re-runs (code is static) — and it is **evidence of presence, never of absence**: it is a partial read that declares its own gaps under `## Not deep-read`, so no agent may infer from its silence that a cited symbol does not exist.
- **`SCRATCH` (`<dir-of-WORKING>/.spec-scratch/run-<RUN>/round-<M>/`) is ephemeral inter-agent plumbing** — regenerated every round, never a source of truth. Safe to delete anytime; cleaned at terminal states.
- If compacted mid-loop, resume from disk: `M` = (count of `round-*.md` in `history/run-<RUN>/`) + 1; re-read paths via `improve_files.py paths <target>`; the digest and `## Open Decisions` are already on disk; the interrupted round simply re-runs (its `SCRATCH` files are overwritten). Continue.

## Briefing writer

Product-altitude prose is produced ONLY here, at the hand-off — never during the loop (while the loop runs, decisions stay working-quality; the reviewer and exit exam read the code and don't need polish). Spawn ONE **briefing-writer** subagent on the **Opus** model and present its output verbatim. It reads the working copy's decisions and TRANSLATES the engineer-written notes for a reader who knows the product but not the code:

```
You are writing the user-facing review of a concept spec's decisions. Fresh eyes.
Read the spec at {absolute WORKING path} — specifically its `## Design Decisions`
(`### Dn:` blocks) and `## Open Decisions` (`### ODn` entries){If non_goals_exists:,
plus the non-goals at {absolute NON_GOALS path}} — the non-goals matter because a
foundational premise often hides in one. Treat every line as raw, engineer-written
notes to be TRANSLATED, not copied.

Write for a reader who knows the PRODUCT but not the code. Every function, column,
or internal coinage goes in a trailing `(impl: …)` clause or is said in plain
words — never in the framing. Produce three markdown lists:

1. FOUNDATIONS — CONFIRM THESE HOLD — the design's few load-bearing architectural
   premises: the cross-cutting commitments and invariants the whole design rests on,
   read off the `### Dn:` decisions AND the non-goals. State each at PRODUCT altitude
   in one or two plain sentences, spelling out its consequence; where it rests on a
   fact only the user can confirm (a cost / scale / vendor-limit / operational
   assumption), end with an explicit *"⚠ rests on: <the assumption> — only you can
   confirm this."* Keep to the genuine SPINE (a handful), not every small choice. If
   a foundational premise is itself an open choice, it also appears in OPEN DECISIONS
   below — reference it ("see OD2"). Number **F1, F2, …**.
2. AUTO-DECISIONS TAKEN — one COMPACT entry per `### Dn:` block, numbered **AD1,
   AD2, …** in order, each tagged with the underlying `Dn` so an override maps back:
   a bold `**ADk — <title>** (Dn)` lead, then 1-3 sentences of what was decided and
   why, plus the main rejected alternative. Scannable.
3. OPEN DECISIONS — one FULL entry per `### ODn`, in this shape:
   **Situation** (what's true today) -> **Problem** (the tension + what breaks if
   it's wrong, and why it needs the user) -> **Options** (open with a one-line axis,
   then each lettered option — keep the source's a/b/c letters exactly — with its
   pros and cons) -> **Recommendation** (the pick by letter + confidence).
   Keep Situation and Problem as SEPARATE beats.

Do not invent decisions or premises that are not in the spec. Preserve option letters exactly.

WORKED EXAMPLE — meta / domain-neutral; mimic the FORM and the raw->polished move,
never the content:

  Foundation — raw signals in the spec (a non-goal + a decision's rationale):
    Non-goal: "session data is not shared across servers." Decision D2: in-process
    cache; rationale notes a shared store is "too much infra to run."
  -> what you write:
    **F1 — Each server keeps its own copy of session data; nothing is shared.** A user
    pinned to a server that gets drained loses their session — there is no shared store
    to fall back to. *⚠ rests on: a shared store being too much infrastructure to
    operate — only you can confirm that.* *(impl: in-process cache, no cross-node
    sharing.)*

  Open decision — raw notes in the spec:
    Situation: in-proc LRU session cache. Problem: multi-node scale, sticky routing
    breaks on node drain, rebalance cost not knowable from code. Options: a) shared
    Redis store — correct under drain, +1 network hop, new infra dep; b) LB affinity
    — no code change, breaks on drain; c) signed client cookie — no store, size cap,
    no revoke. Recommendation: a (moderate), needs infra sign-off.
  -> what you write:
    **OD2 — Where a logged-in user's session lives once we run on more than one server**
    **Situation.** Today each server keeps sessions in its own memory and the load
    balancer pins each user to one server; we're about to run several servers.
    **Problem.** Pinning holds until a server is drained for maintenance — then those
    users get logged out and load skews. Fixing it means relocating session storage,
    and that move's cost can't be read off the code — the part that needs your call.
    **Options** — *correctness-under-failure vs. new infrastructure:*
    - **a — Shared session store** *(recommended)* — survives a server going down and
      balances load; adds a small per-request delay and one new service to operate.
      *(impl: Redis-backed store.)*
    - **b — Pin harder to one server** — no code change, but maintenance still logs
      users out and load stays uneven. *(impl: LB affinity.)*
    - **c — Keep session state in the browser** — nothing to operate, but limited
      size and no forced logout. *(impl: signed cookie.)*
    **Recommendation.** **a**, moderate — escalated only for sign-off on operating
    the new store.

  Taken decision — raw notes -> compact entry:
    Choice: retry transient 5xx, exponential backoff, max 3. Why: clears most flake,
    bounded load. Alternative rejected: infinite retry (thundering herd).
  -> **AD1 — Retry a failed call a few times before giving up** *(D4)*. Transient
    server errors usually clear on a second try; up to 3 retries with growing gaps
    remove most flakiness without hammering a service already struggling (why not
    forever). *(impl: exponential backoff, max 3.)*

Return the three lists as markdown.
```

## On convergence

First clear any pending resume cron for this spec (`CronList` → `CronDelete` the job whose prompt names this target). Then spawn the **briefing writer** (above) and present its output as the **briefing**, in order:
1. **Foundations — confirm these hold** — the writer's `F1, F2, …` block: the design's load-bearing architectural premises at product altitude, each with its consequence and, where relevant, the *"⚠ rests on … only you can confirm"* flag. Present these **first** — they are the spine; if one is wrong, the decisions beneath it don't matter. The user confirms them, or flags one (`Fn`) to re-open.
2. **Auto-decisions taken this run** — the writer's compact entries, numbered `AD1, AD2, …` (each tagged with its underlying `Dn`), one per `### Dn:` written this run (cross-check the count against `CHANGELOG` `[decision-take]` lines). Taken autonomously — invite override by AD number.
3. **Open Decisions** — the writer's full entries (one per `### ODn`). These need the user; they resolve by option letter (e.g. `OD1 = b`) or by editing the spec.
4. **Mechanical fixes** — summarize the run's `[fix]` entries.
5. **Scorecard** (see below).

Then the approval flow (fixes approved independently of non-goals, as `spec-improve`):
- **Accept** → the user has confirmed the auto-decisions and answered the Open Decisions (by option letter, e.g. `OD1 = b`). Finalize the spec so it is **clean and re-runnable**:
  1. **Apply each resolution as settled design.** Fold the chosen option into the section(s) named by that OD's `Governs` line (removing the "OPEN / see ODn" pointers). For a *substantial* resolution (a new mechanism/design), draft it faithfully with a decide/writer agent grounded in the digest + code, then re-run the exit exam over the touched sections; for a *trivial* one (status quo / removal), edit directly. Log each: `improve_files.py append-changelog <target> --run <RUN> --round resolved --kind resolution "ODn = <letter>: <one line of what was folded in>"`.
  2. **Delete each `### ODn` memo** once its resolution is folded in; when all are resolved, **remove the `## Open Decisions` heading entirely.** **Invariant: an accepted spec contains no `## Open Decisions` heading and no `Governs (skip …)` lines** — that is exactly what lets a later re-run *review* the settled content instead of skipping or re-litigating it. (The memos + resolutions live on in `history/run-<RUN>/` snapshots and the archived CHANGELOG, so deleting them from the doc loses no audit trail.)
  3. **Reconcile pass (clean the final artifact).** Spawn ONE **reconcile** subagent on the **Opus** model, handing it the agent instructions at `{MG_INSTALL_RECONCILE_AGENT}`, the absolute `WORKING` path, and **`MODE: full`** (the loop is over, so renumbering is now safe and wanted). It edits `WORKING` **directly** — renumbering the `### Dn:` decisions contiguous and fixing every `Dn` reference, stripping the "reversed-from-as-drafted" / draft-history narrative and stale range/count references, and trimming `Context:` preambles that merely restate the Problem — presentation only, never design content. It self-verifies with `reconcile-audit`; when it returns its one-line summary, **independently confirm** by running `{MG_INSTALL_SCRIPTS_DIR}/improve_files.py reconcile-audit {absolute WORKING path}` yourself and checking `"clean": true`, then **re-run the exit exam over the touched sections** (as in step 1) to confirm the cleanup changed no meaning. If the audit is not clean or the exit exam flags a regression, re-spawn the reconcile agent (or fix + re-audit) before proceeding — never snapshot an unclean artifact.
  4. **Snapshot the finalized copy:** `improve_files.py snapshot <target> --run <RUN> --round resolved` — captures the resolved state in `history/run-<RUN>/` for hindsight analysis.
  5. **Approve:** `improve_files.py approve <target>` (+ `append-non-goal <target> "<text>"` per accepted proposed non-goal). Copies the finalized working copy over the original and archives the CHANGELOG (now carrying the `[resolution]` entries) into `history/run-<RUN>/`. Then `improve_files.py scratch-clean <target>` to remove the ephemeral `.spec-scratch` tree.
  6. **To verify the resolutions**, re-run `/mg:spec-improve-auto <target>`: it cold-starts on the clean settled spec as the next run (history continues), and the reviewer now *reads* the settled content — no skip-lists — to confirm the new design holds.
- **Override an auto-decision, or reject a foundation** → the user names it by its `AD` number (e.g. `AD3`) or a foundation `Fn`; map it to the underlying `### Dn:` block(s) / non-goal via the briefing, re-open it (Edit `WORKING` to back it out / adjust — for a rejected foundation, correct the premise and let the dependent decisions re-derive next round), and re-run.
- **Reject** → `improve_files.py reject <target>` then `improve_files.py scratch-clean <target>` (discards the working copy and the ephemeral scratch tree; the original is untouched — reject never reverts to the pristine `concept.original.md`).

## On round cap

Reaching the cap without a clean exit exam is a signal — usually genuine churn or a cluster of hard escalations. First clear any pending resume cron for this spec (`CronList`/`CronDelete`). Present an honest report: the last exit-exam's substantive findings (read `EXIT_CARRY`, `.spec-scratch/run-<RUN>/exit-carry.md`); what kept churning (from `CHANGELOG`); the `## Open Decisions` list — run it through the **briefing writer** (above) so the escalations read cleanly; the scorecard. Then let the user **re-run** (another batch from `M+1`, e.g. after resolving a blocker), **approve the partial**, or **reject**. Approving a partial runs the same **reconcile pass** (Accept step 3) before `snapshot` + `approve`; a partial keeps its `## Open Decisions`, so their `ODn` references stay live and the audit stays clean.

## On stall

The same two-or-more substantive items survived three consecutive rounds after being routed to a resolver. That is a different signal from the round cap: the loop is not slowly finishing and it is not merely holding steady — it is failing on specific, identified items, and more rounds of the same shape will not resolve them.

First clear any pending resume cron for this spec (`CronList`/`CronDelete`). Then report:
1. **Which items are stuck, and for how long** — the `CARRIED` items by name from `EXIT_CARRY`, cross-referenced against `CHANGELOG` for what was attempted on each. This is the finding; lead with it.
2. **The series** — the `[exit]` lines by round (`DIRTY n CARRIED k`). Present `n` as context, never as the reason: a steady count with low `CARRIED` is progress over changing items, and saying otherwise misreads the instrument.
3. **What the rounds have been doing** — from `CHANGELOG`, whether the recent entries are new ground or repairs of earlier rounds' edits. Repairs dominating is the diagnostic worth naming.
4. **The `## Open Decisions` list**, through the **briefing writer** (above), plus the scorecard.

Then let the user **resolve the open decisions and re-run** (the usual unblock — the escalations are often what the churn is circling), **approve the partial** (same **reconcile pass**, Accept step 3, before `snapshot` + `approve`), **reject**, or **override the stall** and continue to the cap with `--force-continue`. Recommend the first unless the findings say otherwise; do not present continuing as neutral when the series says it is not.

## On usage pause

The round-step-0 gate hit a soft usage limit — stop cleanly and let the run resume itself when the window resets. The working copy is already at a round boundary (nothing was edited this round; the previous round's snapshot stands), so no work is at risk and the original is untouched.

1. **Clear any stale resume** for this spec: `CronList`; `CronDelete` any job whose prompt contains this target path (prevents stacked resumes).
2. **Schedule the resume**: `CronCreate` with `cron` = the gate's `resume_cron`, `recurring` = false, `prompt` = `/mg:spec-improve-auto <absolute target path> --resume`. It fires once, just after the binding window resets, and resumes from disk (digest, working copy, and `## Open Decisions` all persist). This relies on the Claude session staying alive until then — it fires while the session is idle (a persistent terminal/multiplexer session is the assumption).
3. **Report and stop** (do NOT present the convergence briefing — the run is not done):
   ```
   ⏸ Usage pause — session <session_pct>% / weekly <weekly_pct>% (binding: <binding>).
      Auto-resume scheduled for <resume_human>, when the <binding> window resets.
      Work is checkpointed; the original spec is untouched.
      To push now instead: /mg:spec-improve-auto <target> --force
      (runs one more round, then pauses again.)
   ```

## The scorecard

Derive deterministically (do not paraphrase from memory):
- **Rounds run** = `M`.
- **Mechanical fixes** = `grep -c '\[fix\]' <CHANGELOG>`.
- **Auto-decisions taken** = `grep -c '\[decision-take\]' <CHANGELOG>`.
- **Escalated (need you)** = count of entries under `## Open Decisions` in `WORKING`.
- **Exit-exam trend** = `grep '\[exit\]' <CHANGELOG>` — the full `DIRTY n CARRIED k TRUNCATED x` line per round, in order. Report `CARRIED` alongside `n`: a run whose count holds steady while `CARRIED` stays at 0-1 is closing real ground over changing items, which is a different result from one where the same items carry every round, and only `CARRIED` distinguishes them. Note any round where `TRUNCATED` was `yes` — its `n` is a floor, not a measurement.
- **Outcome** = `converged`, `stalled`, or `round-cap`.

</process>

<important_notes>
- **This is a main-session loop, not the Workflow tool.** No `.js` drain, no atom ledger, no verification pyramid, no block-gate, no `DECISIONS.json`. Coverage comes from fresh agents over cheap rounds; decisions are driven by scoped decide-agents; termination by the exit exam. See `docs/work-queue/todo/spec-improve-auto/AUTO2-DESIGN.md`.
- **Drive decisions, don't park them.** Real specs are never decision-complete, so a loop that only surfaces decisions can never converge. Every `DECISION: yes` finding gets a decide-agent that either **takes** it (a defensible resolution is written into the spec — by the applier) or **escalates** it (frames it for the user). Convergence = the exit exam is clean *except* for the escalated Open Decisions.
- **Surface the foundations; don't validate every seam.** The tool cannot atomically check every assumption a spec makes — and shouldn't try. But a design's few load-bearing architectural premises (its ingestion model, its computation invariants, what it deliberately does NOT do) are where a wrong assumption is *obvious to the user at a product level* and usually *unverifiable from code* (it rests on a cost / scale / vendor / operational fact only they hold). So at that altitude the loop's job is to SURFACE the spine for confirmation, not resolve it: the reviewer names the load-bearing premises — reading non-goal *rationales*, not just their scope — and flags any that is unvalidated, inconsistent, or design-flipping-and-user-dependent; such a premise is **escalated, never auto-taken on a guess**; a conflict that is a genuine **design fork** — the two statements encode different intents — is escalated whole, never silently resolved to one side; and the briefing **leads** with a product-altitude "Foundations — confirm these hold" block so the user reviews the spine first. This is the deliberate counterpart to *Drive decisions*: drive the local calls, but hand the architectural premises up.
- **Findings that touch the same decisions are resolved by the same agent.** The reviewer tags each finding with the blocks a fix would edit (`Touches`) and groups findings whose targets intersect into clusters; step 2 spawns one decide-agent per **cluster**, not per finding. One agent per finding is the loop's structural failure mode: two agents resolving two findings that both edit `D13` cannot see each other, so each writes a defensible rule and the pair contradicts. Independent findings still fan out — clustering costs nothing when nothing overlaps.
- **A conflict is either stale text or a real fork, and they route differently.** Most "two decisions disagree" findings are DRAFTING inconsistencies: one fact stated in two places, updated in one. There is no design question in those, and escalating them buries a typo in the user's queue while the contradiction stays in the doc. The cluster agent **takes** them — states the fact once and lists every other site in `IMPACT`. Only a genuine **design fork**, where picking a side changes what gets built, is escalated, and then as one item covering the whole conflict. What is never allowed is resolving half of one.
- **Every take carries its blast radius; the applier applies both as one change.** A decide-agent must search the working copy for every number, count, step label, condition letter and name its edit invalidates, and list them in `IMPACT`. Without that, changing a decision that 100+ other lines restate leaves 100+ stale lines, which the next reviewer reports as fresh contradictions — the loop then spends its rounds repairing its own edits and the exit-exam count stops falling. `EDIT` + `IMPACT` counts as **one** change against the round budget: the impact sites carry no judgment, they are the same fact restated, and applying an edit without them is never the cheaper option.
- **The propose-only rule is enforced by file permissions, not by the prompt.** Step 2 chmods `WORKING` to 444 before spawning the decide-agents and step 3 restores 644 for the applier. This is not belt-and-braces: it was measured — four decide-agents edited one 8,500-line spec concurrently in a round of a loop whose decide prompt states the propose-only rule *twice*. A prompt is not a control when the agent holds `Edit`. Denying the tool instead is not an option worth taking: the `Agent` tool has no per-call tool restriction, so it would mean a custom `subagent_type`, and the read-only agent types (`Explore`, `Plan`) lack **`Write`** as well — which would kill the `handoff-decide-<cluster>.md` file and push every proposed `EDIT` and `IMPACT` list back through the orchestrator's context, defeating **Flat context**. The window denies the write while leaving the handoff file writable, because the handoff file is a `Write` to a fresh path and the clobbering is an `Edit` to `WORKING`. What the concurrent writes cost is not only lost text: they bypass the applier's change budget, its sole-allocator rule for `<NEW-D>` identifiers, and its "two takes editing the same anchor incompatibly → apply neither" refusal. And the loop's own checks cannot see the damage — `floor` and `reconcile-audit` are structural, so a lost concurrent edit disappears with no error and no `CHANGELOG` entry. Two failure modes follow from the window itself and are handled in `improve_files.py`: `shutil.copy2` carries the mode across, so `approve` would otherwise hand back a read-only original, and `init --fresh` — what an operator reaches for after a round dies mid-window — would fail overwriting a 444 working copy. Both clear the bit explicitly. Note the residual honestly: agents keep `Bash`, so this stops drift, not intent.
- **Proposers never allocate identifiers.** Decide-agents write `<NEW-D>` / `<NEW-OPEN-ITEM>` / `<NEW-STEP>` / `<NEW-CONDITION>` placeholders; the applier — already the sole writer — is the sole allocator, assigning numbers across all of a round's proposals at once. Parallel agents all read the same highest existing number, so any number a proposer picks is a number another proposer is also picking. This is the whole fix for duplicate `D9`s and two proposals both claiming "Open Item 8", and it works no matter how many agents a round spawns.
- **The exit exam feeds the next round; it is not a write-only judge.** Its verdict is the loop's termination signal, it holds the highest bar, and it may open code — so it routinely names substance the Sonnet reviewer structurally cannot reach. Its items therefore land in `EXIT_CARRY` at the run root, and step 1's reviewer must **route or explicitly close every one**. Without that path the exam's findings are discarded at the end of each round and the loop resamples from scratch every time: items leave the list without being repaired, the same defect reappears rounds later, and the verdict count stops meaning anything. That failure was measured on a real 8,400-line spec — 18 distinct items across 20 item-slots in four rounds, 8 of them dropped with no repair, one recurring — and it is what the carry file exists to fix.
- **Stop on identity, not on a flat count.** Each round's exit verdict is appended to `CHANGELOG` as an `[exit]` entry (compaction-proof, no second state file), carrying `DIRTY n CARRIED k TRUNCATED x`. The stall trigger is `CARRIED >= 2` for three consecutive rounds: two or more items routed to a resolver and still standing means the loop cannot resolve them, and more rounds of the same shape will not. A steady `n` is NOT that — on a large spec each round closes some items and reaches others the last pass had no room for, so a flat count is the normal shape of progress, and the exam's `TRUNCATED` flag is there because a capped list read as a falling count is how the loop would otherwise convince itself it was converging. `--force-continue` overrides the trigger when the user has looked and disagrees.
- **Read once, branch (via digest).** The cited code is read a single time into `CODE-DIGEST.md`; every reviewer / decide / exit-exam agent reads that small digest instead of re-navigating the codebase (a ~5–10× cost lever). Agents fall back to opening a specific file only when the digest is silent. A genuine fork/shared-context primitive is not available on the Agent path, so the digest is the mechanism. The digest is **facts-only** — never enrich it with run-specific framing (e.g. "escalate this"), which would nudge re-escalation when it is reused across re-runs.
- **Digest silence is not a fact about the code.** The digest is a partial read of the cited surface, so it must declare its gaps under `## Not deep-read`, and no agent may conclude from its silence that a cited function / column / table / file does not exist — that claim needs the file opened. Two rules enforce it where it bites: a fix that deletes, renames or re-points a code citation is `Decision: yes` (it is a factual claim, not a wording change, so it reaches an agent allowed to look), and the applier refuses such a fix if it arrives labelled mechanical. Without them a "mechanical" one-word rename can delete a real function from the spec and substitute a similarly-named one that reads a different table — measured, and it survived three further rounds because nothing routed the exit exam's catch.
- **Measurements are evidence; design parameters are functionality.** A spec's numbers split in two, and only one half is the loop's business. A **design parameter** is a value the spec *chooses* — a threshold, window, limit, retry count, the input set the work is defined over; it *is* what gets built, so exactness and cross-document consistency stay fully load-bearing and nothing here softens them. A **measurement** is a value the spec *observed* about the data at some past moment — `104 of 162`, `2,174 pairs`, a row total; it is evidence *for* a decision, and what carries weight is its magnitude against the threshold that drove that decision, never its digits. The loop has no oracle for the second kind: `DIGEST` is code facts, and a measurement comes from data, so no agent in the loop can re-derive one. That asymmetry is why the split has to be written into the prompts rather than left to judgment. Three mechanisms were otherwise pulling hard toward the digits — the reviewer's `(1) internal contradictions` / `(5) examples that don't match the text` make a drifted restatement the cheapest finding in the document; and the exit exam's substantive bar admitted a wrong count, so an item *nothing in the loop can resolve* entered `EXIT_CARRY`, got routed back to a resolver every round, and accumulated `CARRIED` — manufacturing the exact stall signature the stall check exists to detect. So: the reviewer emits **one** `Decision: no` finding per over-stated measurement (state it once at magnitude, with provenance — what it was measured over and roughly when — and delete the restatements), never one contradiction per disagreeing site; and the exit exam does not count measurement imprecision at all. The single substantive case is a *decision*, not a number: the choice a measurement grounds would flip at a plausible different value and the spec never recorded what it was taken over — that is an unvalidated assumption for the user, not arithmetic to go redo. Provenance is what keeps the softened form falsifiable: "~2/3 of the universe, measured 2026-06 over ~160 tickers" can still be checked and dates itself; a bare `104 of 162` cannot.
- **Flat context — the orchestrator is a router.** The main loop never reads or edits `WORKING`; each round it hands subagents file paths and reads back one-line summaries, so the spec text, the findings, and the proposed edits never enter the main context (they flow agent → `SCRATCH`/`WORKING` → agent). Decide-agents *propose* — each writes one `handoff-decide-<cluster>.md`, none touches the spec; a single **applier** subagent is the sole writer, the sole allocator of identifiers, and also drives the deterministic floor. This is the sibling cost lever to the digest: the digest keeps *code* out of every agent's context; the router keeps *spec churn* out of the orchestrator's — together they let a 20-round run stay well under the context ceiling instead of degrading after 3–4 rounds.
- **Model tiers.** Digest-reader + reviewer + **applier** = **Sonnet** (heavy readers / mechanical transcription; a reviewer miss or a mis-placed edit is self-correcting across rounds — and the applier writes edit *text authored verbatim by the Opus decide-agents*, so it exercises no design judgment of its own: allocating a number is highest-plus-one, and its one refusal rule — two takes editing the same anchor incompatibly — resolves to *defer both*, never to pick). Decide-agent + exit-exam + reconcile + briefing writer = **Opus** (sharp judgment / user-facing prose; a bad auto-take is written into the spec and a false-CLEAN ends the loop — neither is self-correcting).
- **Decisions are working-quality during the loop; polished only at the hand-off.** Decide-agents write functional decisions (accuracy over prose); the reviewer and exit exam read the code and don't need polish. A single **briefing writer** produces the product-altitude prose once, when the run surfaces to the user (convergence or round cap) — keeping the per-round path lean and prose-writing out of the main loop's context. The concept's own `### Dn:` decision text stays implementer-facing, per the template.
- **Escalation safety, without a ledger.** Blast radius is enumerated by the decide-agent in `IMPACT`, not computed from a dependency graph. Mitigations: the decide-agent is Opus and sees every block in its cluster; the working copy is the safety net (original untouched until approve); and every auto-take is in the briefing and the changelog — visible and reversible, never silently locked in.
- **`## Open Decisions` is loop-owned and lives in the working copy.** It is the escalation record and the reviewers' skip-list (like non-goals). On approval the user resolves it; it is not meant to ship unresolved.
- **Asymmetric bars.** The step-1 reviewer is deliberately harsh and wide; the step-6 exit exam holds a high, substantive-only bar. That asymmetry is what lets the loop converge when substantive issues (and their decisions) are handled, even if a harsh reviewer could always find one more nitpick.
- **The working copy is the safety net and the only durable state.** The orchestrator holds no durable round state — and, per **Flat context**, no round *content* either; it routes paths, re-reads from disk, and is resilient to mid-loop compaction. `SCRATCH` is ephemeral plumbing, never a source of truth.
- **Usage-limit gate + self-scheduled resume.** Round step 0 reads the real Claude Code `/usage` (cost-free) and **pauses** the run when session > 75% or weekly > 90%, scheduling its own `--resume` at the binding window's reset via a one-shot `CronCreate` (session-only — it needs this session to stay alive, which a persistent terminal/multiplexer session provides). `--force` grants exactly one over-threshold round (via the `FORCE_MARKER` token), then the loop pauses again. Whenever the loop ends for any *other* reason — convergence, round cap, approve, reject — clear any pending resume cron for this spec (`CronList`/`CronDelete`) so a stale resume can't fire.
- **Reconcile pass, in two modes.** The cleanup that renumbers decisions + fixes cross-refs, strips draft-history narrative, and dedupes `Context:` vs Problem lives in its OWN agent file `agents/spec-reconcile.md` — not inline, because it is a whole-document transform uncoupled from the round/handoff protocol (the per-round agents stay inline). It edits `WORKING` directly (a bulk transform, so the per-round "propose-only" rule does not apply), guarded by `improve_files.py reconcile-audit` (deterministic: contiguous numbering + zero dangling `Dn`/`ODn` refs) plus an exit-exam re-check. It runs at **finalize** in `MODE: full`, and **every 3rd round** in `MODE: cleanup-only` — same agent, minus renumbering, because mid-loop renumbering would re-point every `Dn` already written into `CHANGELOG` and into the `Governs` skip-lists. The mid-loop run is the loop's only downward pressure on document size; without it every round appends and nothing ever retires. **Install wiring:** `install.sh` copies the `agents/` dir to `<target>/spec/agents/`, seds `{MG_INSTALL_RECONCILE_AGENT}` → the deployed agent file's path, and seds `{MG_INSTALL_SCRIPTS_DIR}` *inside* the agent file (the same substitution the commands get). The `reconcile-audit` subcommand rides the existing `{MG_INSTALL_SCRIPTS_DIR}` wiring — no new script placeholder.
</important_notes>
