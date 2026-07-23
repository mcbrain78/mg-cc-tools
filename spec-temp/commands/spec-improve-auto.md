# Spec Improve Auto

---
name: mg-temp:spec-improve-auto
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
Refine a concept spec autonomously, without a per-round human gate. This command drives a loop **in the main session** (like `mg-temp:spec-improve`, not the Workflow tool). Its job is to **drive through decision points**, not just surface them: each round it reviews the spec with fresh eyes, resolves the decisions it can defend, **escalates** only the ones that genuinely need a human, enforces a deterministic structural floor, and asks a fresh **exit exam** whether anything substantive is still wrong. It loops until the exit exam is clean *except for the escalated decisions* (converged) or a round cap is hit.

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

   Usage: /mg-temp:spec-improve-auto <file-path> [--resume] [--force]

   Example:
     /mg-temp:spec-improve-auto docs/work-queue/todo/worktrees/concept.md
   ```
   Exit.

   **Flags** (parsed from `$ARGUMENTS`, order-independent):
   - `--resume` — a scheduled or manual resume: at the D7 guard (step 3) auto-**Resume** the existing working copy with no AskUserQuestion. If no working copy exists, fall through to a normal cold start.
   - `--force` — a one-round usage-gate override (implies `--resume`): after binding paths, write an empty `FORCE_MARKER`; the next usage gate (round step 0) consumes it to run exactly one round past the soft limit, then normal gating resumes.

2. Read the target file. If it doesn't exist or is empty, report the error and exit.

3. **Guarded init.** Run:
   ```
   uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py init <target-file-path>
   ```
   - **On success (exit 0):** capture the emitted resolved-paths JSON. Store it as `PATHS_JSON`. If `backup_created` is true, report: `Backed up original to <original_backup>`.
   - **On guard-fail (exit 1):** an in-progress working copy from a prior session exists (the D7 guard). Do **not** overwrite it. **If `--resume` or `--force` is set** (a scheduled or manual resume), auto-**Resume**: run the read-only `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py paths <target-file-path>`, use its JSON as `PATHS_JSON`, and skip the question. **Otherwise** run `paths`, surface the leftover state, and use **AskUserQuestion** for the binary choice:
     - **Resume** — continue with the existing working copy. Use the `paths` JSON as `PATHS_JSON`.
     - **Discard and restart** — run `improve_files.py init <target-file-path> --fresh` (then `improve_files.py scratch-clean <target-file-path>` to clear any stale scratch), and use the init JSON.

     This AskUserQuestion is the **only** picker before convergence (a `--resume`/`--force` invocation skips even this). The loop is otherwise autonomous.

   Bind from `PATHS_JSON`:
   - `WORKING` = `auto_improve` (every edit lands here)
   - `NON_GOALS` = `non_goals` (may not exist yet; `non_goals_exists` tells you)
   - `CHANGELOG` = `changelog`
   - `RUN` = `next_run`
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

Return one line: the digest path + entity count.
```

   If `DIGEST` already exists (a re-run, or a resumed session), **reuse it** — code is static across a refinement run. (Only refresh if the user says the code changed: delete `DIGEST` and re-run Step 0.)

## The auto-loop

Rounds `M = 1, 2, 3, …` up to the **round cap of 20**. Each round is self-contained (see **State discipline**).

**The orchestrator is a thin router — it never reads or edits `WORKING` itself.** Each round it spawns subagents, hands them **absolute file paths**, and gets back only **one-line summaries** (ids, counts, a verdict word). All bulky content — the spec text, the findings, the proposed edits — flows agent → disk → agent through a per-round scratch dir and never enters the main context; that is what keeps context flat across a long run. At the **start of every round**, resolve (and create) that dir, capturing the absolute path it prints:
`uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py scratch-dir <target> --run <RUN> --round <M>` → store as `SCRATCH`.
Hand `<SCRATCH>/findings.md`, `<SCRATCH>/decide-<id>.md`, and `<SCRATCH>/exit.md` to the agents below. A round:

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
need.
{If non_goals_exists: Also read {absolute NON_GOALS path} — do not flag issues
that fall under a listed non-goal (severe bugs excepted).}
Also read the concept spec template at: {absolute template path} — assess whether
expected sections are present and adequately filled.

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
not bodies; (9) verification coverage — every `### What gets built` bullet needs
a matching Verification item; (10) citation discipline — every top-level bullet
in `### What gets built` must cite `(Dx)` referencing a real `### Dn:` block.

Be harsh. Validate claims against the digest.

WRITE your findings to {absolute SCRATCH/findings.md path} — one block per finding:
  ## <id> — [SEVERITY] <section/line>
  Problem: <what is wrong>
  Fix: <suggested fix, or "none">
  Decision: <yes|no>
  NeedsUser: <yes|no>
  (<id> = F1, F2, …; SEVERITY = critical | major | minor.
   Decision = yes if resolving it is a design decision — a choice among
     alternatives, a premise to correct, an open question/deferral to close;
     no if it is a mechanical/clarity fix.
   NeedsUser = yes only if the decision genuinely needs a human — changes intent/
     scope, high-stakes, or you cannot determine the right answer even from the code.)
Then RETURN ONLY this compact index — no prose, no finding bodies:
  FINDINGS: {absolute SCRATCH/findings.md path}
  MECH: <count of Decision:no findings>
  DECISIONS:
    <id> — <≤8-word gist>[ NEEDS_USER]   (one line per Decision:yes finding)
If nothing worth flagging: write findings.md with just a heading and return exactly NO ISSUES.
```

### 2 — Drive the decisions (Opus — take or escalate; propose only, one file each)
For each `<id>` in the reviewer's DECISIONS index (there is no need to read `findings.md` yourself — pass the id along), spawn a **decide** subagent on the **Opus** model. Spawn them **in parallel** (in one message): each only reads and writes its own file, so there is no contention. A wrong take gets written into the spec, so this stays Opus. Each decide-agent reads its one finding from `findings.md`, may open a specific source file under `CODE_ROOT` if the digest is thin, and **writes its result to disk — it never edits the spec** (a single applier is the sole writer):

```
You are resolving ONE design decision in a concept spec. Fresh eyes, no prior
context. You only PROPOSE — you do NOT edit the spec (a single applier writes it).
Spec (read-only): {absolute WORKING path}   Code-facts digest: {absolute DIGEST path}
Findings: {absolute SCRATCH/findings.md path} — resolve the finding with id "{id}".
(open a specific file under {absolute CODE_ROOT} only if the digest lacks a fact
you need). {If non_goals_exists: Non-goals: {absolute NON_GOALS path}.}

Read that one finding, research it against the digest/code, then choose ONE and
WRITE your result to {absolute SCRATCH/decide-{id}.md} in exactly this shape:

TAKE — if there is a clearly defensible answer, its blast radius is bounded (it
does not ripple across many sections), and it does NOT reverse a stated non-goal
or the spec's evident intent:
  ACTION: take
  CHANGELOG: <one line: what was decided>
  EDIT:
  <the exact new/replacement spec text AND where it goes — a repaired or new
   `### Dn:` decision block (Choice / Why / Alternatives rejected, per the
   template), a corrected premise, a resolved open item. Contracts/prose, never
   implementation code. Name the anchor precisely (e.g. 'replace the paragraph
   starting "…"' or 'append as a new ### D9 under ## Design Decisions'). Write it
   FUNCTIONALLY — accuracy over polish; the briefing writer polishes later.>

ESCALATE — if the answer is genuinely ambiguous, high-stakes, wide-blast-radius,
or would reverse intent/a non-goal (functional notes are fine — the briefing writer
polishes the prose later; just be accurate and complete):
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

Default to TAKE when you can defend it; escalate only what truly needs the human.
RETURN ONLY one line:  {id} take — <≤10-word gist>   OR   {id} escalate — <≤10-word gist>
```

Each decide-agent returns one line (`{id} take|escalate — <gist>`); the orchestrator holds only those lines. The actual edit text and escalation beats stay in the `decide-<id>.md` files for the applier.

### 3 — Apply the round (Sonnet — the sole writer; transcribes, does not judge)
Spawn ONE **applier** subagent on the **Sonnet** model. It is the *only* thing that writes `WORKING` this round: it transcribes the already-decided changes (the judgment happened in Steps 1–2), so it exercises no judgment — a mis-placed edit is self-correcting (the next reviewer re-flags it) and the edit *text* is authored verbatim by the Opus decide-agents. It **always runs** (it also owns the deterministic floor), even when there is nothing to apply:

```
You are the applier: the SOLE writer of a concept spec this round. You TRANSCRIBE
already-decided changes; you do NOT re-judge them.
Spec (edit in place): {absolute WORKING path}
Findings: {absolute SCRATCH/findings.md path}
Decisions: every {absolute SCRATCH}/decide-*.md file (there may be none).

Budget: apply at most 10 changes TOTAL (mechanical fixes + TAKE edits), highest
severity first (a TAKE's severity is that of its originating finding in findings.md,
matched by id); leave the rest — they re-surface next round. Escalations do NOT
count against the budget.

1. MECHANICAL FIXES — for each finding in findings.md with `Decision: no`, apply its
   `Fix` (prose/contract only, NEVER implementation code). A "missing piece" that
   needs a design choice is a decision, not a fix — skip it here.
2. TAKE — for each decide-*.md with `ACTION: take`, apply its `EDIT` VERBATIM at the
   location it names. Do NOT reword the edit text.
3. ESCALATE — for each with `ACTION: escalate`, append an `### ODn — <TITLE>` entry to
   the `## Open Decisions` section (create it once, near the end, before
   `## Verification` if present, else at end) from the fields: **Situation**,
   **Problem**, lettered **Options** (keep the a/b/c letters exactly) with tradeoffs,
   **Recommendation**, then a closing `Governs (skip in review until resolved): <GOVERNS>`
   line. Number `ODn` after any existing OD entries. Keep it functional.
4. If an edit does NOT apply cleanly (anchor missing / conflict), SKIP it and report
   it — never improvise.
5. FLOOR — run `uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py floor {absolute WORKING path}`;
   its findings (missing required headings, uncited bullets) are safe mechanical
   fixes — apply and re-run until it exits 0.
6. LOG — one call per applied change:
   `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py append-changelog {TARGET_ABS} --run {RUN} --round {M} --kind fix|decision-take "<one line>"`
   (use the decide-agent's CHANGELOG line for takes; the finding's Problem for fixes).

RETURN ONLY:
  APPLIED fixes=<a> takes=<b> escalations=<c> skipped=<s>
  (if s>0, one extra line per skip:  SKIP <id> — <why>)
```

### 4 — Snapshot
`uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py snapshot <target> --run <RUN> --round <M>` (writes `history/run-<RUN>/round-<M>.md`; do not read it back). This is the round's resume anchor; the floor already passed inside the applier.

### 5 — Exit exam (Opus — drives termination)
Spawn ONE exit-exam subagent on the **Opus** model — a higher, substantive-only bar than Step 1:

```
You are doing a final readiness check on a concept spec. Fresh eyes, no context.
Spec: {absolute WORKING path}   Code-facts digest: {absolute DIGEST path}
(open a file under {absolute CODE_ROOT} only if a substantive judgment needs it).
{If non_goals_exists: Non-goals: {absolute NON_GOALS path}.}

Is anything SUBSTANTIVE still wrong or missing — something that would make an
implementer build the wrong thing, get blocked, or have to come back and ask?
Ignore cosmetic nitpicks and anything under a listed non-goal.

Do NOT count anything already listed under the spec's `## Open Decisions` heading,
or any spec section named in an Open Decision's **Governs** line — those are known
and deliberately escalated to the user; treat them as resolved for the purposes of
this check.

If nothing substantive remains (outside `## Open Decisions`), return exactly: CLEAN
Otherwise WRITE the short list to {absolute SCRATCH/exit.md path} (one line each:
`- [SEVERITY] <section> — <what is substantively wrong>. DECISION: <yes|no>.`) and
RETURN ONLY: DIRTY <n>   (n = number of substantive items)
```

### 6 — Converge or continue
Branch on the exit-exam's one-line verdict alone — you hold no round content:
- **`CLEAN` (and the floor passed — the applier drove it to 0) → CONVERGED.** Go to **On convergence**.
- **`DIRTY <n>` → next round.** Carry nothing in context; the next round's fresh agents re-derive from the updated `WORKING` + the digest. Increment `M`.
- **`M` reaches 20 without converging → STOP at cap.** Go to **On round cap**.

## State discipline (load-bearing)

The orchestrator keeps **nothing durable in its own context** — and, in the flat-context loop, almost nothing *transient* either:
- **The orchestrator never reads or edits `WORKING`.** Every round it only spawns agents with paths and reads back one-line summaries. All spec text, findings, and proposed edits live in files (the per-round `SCRATCH` dir and `WORKING`), read and written by subagents whose context is discarded on return. This is what holds the main context flat over a 20-round run.
- **`WORKING` on disk is the state.** Unresolved issues persist because they are still in the doc; the reviewer re-derives the canonical live list each round. Never filter a finding using memory of a prior round.
- **`## Open Decisions` in `WORKING` is the escalation memory** — an escalated decision lives there, so future reviewers skip it and it is not re-researched (the same mechanism as `NON_GOALS`). This is the one durable cross-round record, and it lives in the doc, not your context.
- **`DIGEST` is computed once and reused** every round and across re-runs (code is static).
- **`SCRATCH` (`<dir-of-WORKING>/.spec-scratch/run-<RUN>/round-<M>/`) is ephemeral inter-agent plumbing** — regenerated every round, never a source of truth. Safe to delete anytime; cleaned at terminal states.
- If compacted mid-loop, resume from disk: `M` = (count of `round-*.md` in `history/run-<RUN>/`) + 1; re-read paths via `improve_files.py paths <target>`; the digest and `## Open Decisions` are already on disk; the interrupted round simply re-runs (its `SCRATCH` files are overwritten). Continue.

## Briefing writer

Product-altitude prose is produced ONLY here, at the hand-off — never during the loop (while the loop runs, decisions stay working-quality; the reviewer and exit exam read the code and don't need polish). Spawn ONE **briefing-writer** subagent on the **Opus** model and present its output verbatim. It reads the working copy's decisions and TRANSLATES the engineer-written notes for a reader who knows the product but not the code:

```
You are writing the user-facing review of a concept spec's decisions. Fresh eyes.
Read the spec at {absolute WORKING path} — specifically its `## Design Decisions`
(`### Dn:` blocks) and `## Open Decisions` (`### ODn` entries). Treat every line
as raw, engineer-written notes to be TRANSLATED, not copied.

Write for a reader who knows the PRODUCT but not the code. Every function, column,
or internal coinage goes in a trailing `(impl: …)` clause or is said in plain
words — never in the framing. Produce two markdown lists:

1. AUTO-DECISIONS TAKEN — one COMPACT entry per `### Dn:` block, numbered **AD1,
   AD2, …** in order, each tagged with the underlying `Dn` so an override maps back:
   a bold `**ADk — <title>** (Dn)` lead, then 1-3 sentences of what was decided and
   why, plus the main rejected alternative. Scannable.
2. OPEN DECISIONS — one FULL entry per `### ODn`, in this shape:
   **Situation** (what's true today) -> **Problem** (the tension + what breaks if
   it's wrong, and why it needs the user) -> **Options** (open with a one-line axis,
   then each lettered option — keep the source's a/b/c letters exactly — with its
   pros and cons) -> **Recommendation** (the pick by letter + confidence).
   Keep Situation and Problem as SEPARATE beats.

Do not invent decisions that are not in the spec. Preserve option letters exactly.

WORKED EXAMPLE — meta / domain-neutral; mimic the FORM and the raw->polished move,
never the content:

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

Return the two lists as markdown.
```

## On convergence

First clear any pending resume cron for this spec (`CronList` → `CronDelete` the job whose prompt names this target). Then spawn the **briefing writer** (above) and present its output as the **briefing**, in order:
1. **Auto-decisions taken this run** — the writer's compact entries, numbered `AD1, AD2, …` (each tagged with its underlying `Dn`), one per `### Dn:` written this run (cross-check the count against `CHANGELOG` `[decision-take]` lines). Taken autonomously — invite override by AD number.
2. **Open Decisions** — the writer's full entries (one per `### ODn`). These need the user; they resolve by option letter (e.g. `OD1 = b`) or by editing the spec.
3. **Mechanical fixes** — summarize the run's `[fix]` entries.
4. **Scorecard** (see below).

Then the approval flow (fixes approved independently of non-goals, as `spec-improve`):
- **Accept** → the user has confirmed the auto-decisions and answered the Open Decisions (by option letter, e.g. `OD1 = b`). Finalize the spec so it is **clean and re-runnable**:
  1. **Apply each resolution as settled design.** Fold the chosen option into the section(s) named by that OD's `Governs` line (removing the "OPEN / see ODn" pointers). For a *substantial* resolution (a new mechanism/design), draft it faithfully with a decide/writer agent grounded in the digest + code, then re-run the exit exam over the touched sections; for a *trivial* one (status quo / removal), edit directly. Log each: `improve_files.py append-changelog <target> --run <RUN> --round resolved --kind resolution "ODn = <letter>: <one line of what was folded in>"`.
  2. **Delete each `### ODn` memo** once its resolution is folded in; when all are resolved, **remove the `## Open Decisions` heading entirely.** **Invariant: an accepted spec contains no `## Open Decisions` heading and no `Governs (skip …)` lines** — that is exactly what lets a later re-run *review* the settled content instead of skipping or re-litigating it. (The memos + resolutions live on in `history/run-<RUN>/` snapshots and the archived CHANGELOG, so deleting them from the doc loses no audit trail.)
  3. **Snapshot the finalized copy:** `improve_files.py snapshot <target> --run <RUN> --round resolved` — captures the resolved state in `history/run-<RUN>/` for hindsight analysis.
  4. **Approve:** `improve_files.py approve <target>` (+ `append-non-goal <target> "<text>"` per accepted proposed non-goal). Copies the finalized working copy over the original and archives the CHANGELOG (now carrying the `[resolution]` entries) into `history/run-<RUN>/`. Then `improve_files.py scratch-clean <target>` to remove the ephemeral `.spec-scratch` tree.
  5. **To verify the resolutions**, re-run `/mg-temp:spec-improve-auto <target>`: it cold-starts on the clean settled spec as the next run (history continues), and the reviewer now *reads* the settled content — no skip-lists — to confirm the new design holds.
- **Override an auto-decision** → the user names it by its `AD` number (e.g. `AD3`); map it to the underlying `### Dn:` block via the briefing, re-open it (Edit `WORKING` to back it out / adjust), and re-run.
- **Reject** → `improve_files.py reject <target>` then `improve_files.py scratch-clean <target>` (discards the working copy and the ephemeral scratch tree; the original is untouched — reject never reverts to the pristine `concept.original.md`).

## On round cap

Reaching the cap without a clean exit exam is a signal — usually genuine churn or a cluster of hard escalations. First clear any pending resume cron for this spec (`CronList`/`CronDelete`). Present an honest report: the last exit-exam's substantive findings (read `<SCRATCH for the final round>/exit.md`); what kept churning (from `CHANGELOG`); the `## Open Decisions` list — run it through the **briefing writer** (above) so the escalations read cleanly; the scorecard. Then let the user **re-run** (another batch from `M+1`, e.g. after resolving a blocker), **approve the partial**, or **reject**.

## On usage pause

The round-step-0 gate hit a soft usage limit — stop cleanly and let the run resume itself when the window resets. The working copy is already at a round boundary (nothing was edited this round; the previous round's snapshot stands), so no work is at risk and the original is untouched.

1. **Clear any stale resume** for this spec: `CronList`; `CronDelete` any job whose prompt contains this target path (prevents stacked resumes).
2. **Schedule the resume**: `CronCreate` with `cron` = the gate's `resume_cron`, `recurring` = false, `prompt` = `/mg-temp:spec-improve-auto <absolute target path> --resume`. It fires once, just after the binding window resets, and resumes from disk (digest, working copy, and `## Open Decisions` all persist). This relies on the Claude session staying alive until then — it fires while the session is idle (a persistent terminal/multiplexer session is the assumption).
3. **Report and stop** (do NOT present the convergence briefing — the run is not done):
   ```
   ⏸ Usage pause — session <session_pct>% / weekly <weekly_pct>% (binding: <binding>).
      Auto-resume scheduled for <resume_human>, when the <binding> window resets.
      Work is checkpointed; the original spec is untouched.
      To push now instead: /mg-temp:spec-improve-auto <target> --force
      (runs one more round, then pauses again.)
   ```

## The scorecard

Derive deterministically (do not paraphrase from memory):
- **Rounds run** = `M`.
- **Mechanical fixes** = `grep -c '\[fix\]' <CHANGELOG>`.
- **Auto-decisions taken** = `grep -c '\[decision-take\]' <CHANGELOG>`.
- **Escalated (need you)** = count of entries under `## Open Decisions` in `WORKING`.
- **Outcome** = `converged` or `round-cap`.

</process>

<important_notes>
- **This is a main-session loop, not the Workflow tool.** No `.js` drain, no atom ledger, no verification pyramid, no block-gate, no `DECISIONS.json`. Coverage comes from fresh agents over cheap rounds; decisions are driven by scoped decide-agents; termination by the exit exam. See `docs/work-queue/todo/spec-improve-auto/AUTO2-DESIGN.md`.
- **Drive decisions, don't park them.** Real specs are never decision-complete, so a loop that only surfaces decisions can never converge. Every `DECISION: yes` finding gets a decide-agent that either **takes** it (a defensible resolution is written into the spec — by the applier) or **escalates** it (frames it for the user). Convergence = the exit exam is clean *except* for the escalated Open Decisions.
- **Read once, branch (via digest).** The cited code is read a single time into `CODE-DIGEST.md`; every reviewer / decide / exit-exam agent reads that small digest instead of re-navigating the codebase (a ~5–10× cost lever). Agents fall back to opening a specific file only when the digest is silent. A genuine fork/shared-context primitive is not available on the Agent path, so the digest is the mechanism. The digest is **facts-only** — never enrich it with run-specific framing (e.g. "escalate this"), which would nudge re-escalation when it is reused across re-runs.
- **Flat context — the orchestrator is a router.** The main loop never reads or edits `WORKING`; each round it hands subagents file paths and reads back one-line summaries, so the spec text, the findings, and the proposed edits never enter the main context (they flow agent → `SCRATCH`/`WORKING` → agent). Decide-agents *propose* — each writes one `decide-<id>.md`, none touches the spec; a single **applier** subagent is the sole writer and also drives the deterministic floor. This is the sibling cost lever to the digest: the digest keeps *code* out of every agent's context; the router keeps *spec churn* out of the orchestrator's — together they let a 20-round run stay well under the context ceiling instead of degrading after 3–4 rounds.
- **Model tiers.** Digest-reader + reviewer + **applier** = **Sonnet** (heavy readers / mechanical transcription; a reviewer miss or a mis-placed edit is self-correcting across rounds — and the applier writes edit *text authored verbatim by the Opus decide-agents*, so it exercises no judgment of its own). Decide-agent + exit-exam + briefing writer = **Opus** (sharp judgment / user-facing prose; a bad auto-take is written into the spec and a false-CLEAN ends the loop — neither is self-correcting).
- **Decisions are working-quality during the loop; polished only at the hand-off.** Decide-agents write functional decisions (accuracy over prose); the reviewer and exit exam read the code and don't need polish. A single **briefing writer** produces the product-altitude prose once, when the run surfaces to the user (convergence or round cap) — keeping the per-round path lean and prose-writing out of the main loop's context. The concept's own `### Dn:` decision text stays implementer-facing, per the template.
- **Escalation safety, without a ledger.** Blast radius is judged by the decide-agent, not computed. Mitigations: the decide-agent is Opus; the working copy is the safety net (original untouched until approve); and every auto-take is in the briefing and the changelog — visible and reversible, never silently locked in.
- **`## Open Decisions` is loop-owned and lives in the working copy.** It is the escalation record and the reviewers' skip-list (like non-goals). On approval the user resolves it; it is not meant to ship unresolved.
- **Asymmetric bars.** The Step-1 reviewer is deliberately harsh and wide; the Step-5 exit exam holds a high, substantive-only bar. That asymmetry is what lets the loop converge when substantive issues (and their decisions) are handled, even if a harsh reviewer could always find one more nitpick.
- **The working copy is the safety net and the only durable state.** The orchestrator holds no durable round state — and, per **Flat context**, no round *content* either; it routes paths, re-reads from disk, and is resilient to mid-loop compaction. `SCRATCH` is ephemeral plumbing, never a source of truth.
- **Usage-limit gate + self-scheduled resume.** Round step 0 reads the real Claude Code `/usage` (cost-free) and **pauses** the run when session > 75% or weekly > 90%, scheduling its own `--resume` at the binding window's reset via a one-shot `CronCreate` (session-only — it needs this session to stay alive, which a persistent terminal/multiplexer session provides). `--force` grants exactly one over-threshold round (via the `FORCE_MARKER` token), then the loop pauses again. Whenever the loop ends for any *other* reason — convergence, round cap, approve, reject — clear any pending resume cron for this spec (`CronList`/`CronDelete`) so a stale resume can't fire.
</important_notes>
