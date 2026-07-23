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
     - **Discard and restart** — run `improve_files.py init <target-file-path> --fresh`, then use its JSON.

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

5. **Absolutize the paths handed to subagents** — `WORKING`, `NON_GOALS`, `DIGEST`, `{MG_INSTALL_CONCEPT_TEMPLATE}`, `CODE_ROOT`. Rule: if a path does not begin with `/`, prepend `<cwd>/`. Subagent cwd is not guaranteed, so every path in an agent prompt is absolute. The command's own `uv run` / `Read` / `Edit` calls stay relative to `WORKING`.

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

Rounds `M = 1, 2, 3, …` up to the **round cap of 20**. Each round is self-contained (see **State discipline**). A round:

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

Return findings as a compact list, one entry each, exactly:
  - [SEVERITY] <section/line> — <what is wrong>. FIX: <suggested fix, or "none">. DECISION: <yes|no>. NEEDS_USER: <yes|no>.
  SEVERITY = critical | major | minor.
  DECISION = yes if resolving it is a design decision (a choice among alternatives,
    a premise to correct, an open question/deferral to close), no if it is a
    mechanical/clarity fix.
  NEEDS_USER = yes only if the decision genuinely needs a human (changes intent/
    scope, high-stakes, or you cannot determine the right answer even from the
    code). Otherwise no.
If nothing worth flagging: return exactly NO ISSUES.
```

### 2 — Triage the mechanical fixes
Apply, on `WORKING`, every `DECISION: no` finding you are confident resolves the issue without changing intent/scope (Read `WORKING`, then `Edit`). Resolve "missing piece" findings by specifying the contract in prose — never implementation code. Log each: `improve_files.py append-changelog <target> --run <RUN> --round <M> --kind fix "<desc>"`.

### 3 — Drive the decisions (Opus — take or escalate)
For each `DECISION: yes` finding (skip any whose subject already appears under `## Open Decisions`), spawn a **decide** subagent on the **Opus** model (sharp — a wrong take gets written into the spec). Give it the one finding, the digest, and permission to open specific source files under `CODE_ROOT` if the digest is thin:

```
You are resolving ONE design decision in a concept spec. Fresh eyes, no prior
context.
Spec: {absolute WORKING path}   Code-facts digest: {absolute DIGEST path}
(open a specific file under {absolute CODE_ROOT} only if the digest lacks a fact
you need). {If non_goals_exists: Non-goals: {absolute NON_GOALS path}.}

The decision to resolve:
{paste the one finding: severity, location, what's wrong, suggested fix}

Research it against the digest/code, then choose ONE:

TAKE — if there is a clearly defensible answer, its blast radius is bounded (it
does not ripple across many sections), and it does NOT reverse a stated non-goal
or the spec's evident intent. Return:
  VERDICT: TAKE
  RATIONALE: <why this answer, with the evidence>
  ALTERNATIVES_REJECTED: <the main alternative(s) and why not>
  EDIT: <the exact new/replacement spec text and where it goes — a repaired or
        new `### Dn:` decision block (Choice / Why / Alternatives rejected, per the
        template), a corrected premise, a resolved open item. Contracts/prose,
        never implementation code. Write it FUNCTIONALLY — accuracy over polish;
        the product-altitude prose is produced later by the briefing writer.>

ESCALATE — if the answer is genuinely ambiguous, high-stakes, wide-blast-radius,
or would reverse intent/a non-goal. Return the SUBSTANCE (functional notes are
fine — the briefing writer polishes the prose later; just be accurate and
complete):
  VERDICT: ESCALATE
  SITUATION: <the relevant state of the world, 1-2 sentences>
  PROBLEM: <the tension that forces a choice, and why you cannot just take it
           (genuinely ambiguous / high-stakes / would reverse intent)>
  OPTIONS: <the REAL options — usually 2-4; do NOT pad to a fixed count. Label each
           with a sequential lowercase letter a, b, c, … and give its tradeoff
           (pros/cons). The letters are what the user types back.>
  RECOMMENDATION: <your lean named by its letter (e.g. "b") + confidence, and the
                  one reason it wins>
  GOVERNS: <the spec sections/decisions this choice controls, so review skips them
           until it is resolved — e.g. "the WASO solution section, D1, D8, D10">

Default to TAKE when you can defend it; escalate only what truly needs the human.
```

For each result:
- **TAKE** → apply `EDIT` to `WORKING` (Read then Edit), and log: `append-changelog <target> --run <RUN> --round <M> --kind decision-take "<one-line: what was decided>"`.
- **ESCALATE** → append the decision to the `## Open Decisions` section of `WORKING` (create the section once, near the end, before `## Verification` if present, else at end) as an `### ODn — <title>` entry carrying the agent's functional beats — **Situation**, **Problem**, lettered **Options** (a, b, c …) with tradeoffs, **Recommendation** — and closing with a **Governs (skip in review until resolved):** line listing its `GOVERNS` sections. Keep it functional; the briefing writer produces the user-facing prose at convergence. Being in the doc — including the Governs list — it is invisible to the sections future reviewers would otherwise re-flag.

**Round budget:** apply at most **10 changes** (fixes + takes) to `WORKING` per round. If more clear the bar, take the 10 highest-severity; the rest re-surface next round. Escalations do not count against the budget (they are cheap appends).

### 4 — Deterministic floor + snapshot
`uv run {MG_INSTALL_SCRIPTS_DIR}/spec_checks.py floor <WORKING>` must pass. On exit 1, its findings (missing required headings, uncited bullets) are safe mechanical fixes — apply, log, re-run until it passes. Then:
`uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py snapshot <target> --run <RUN> --round <M>` (writes `history/run-<RUN>/round-<M>.md`; do not read it back).

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

If nothing substantive remains (outside `## Open Decisions`), return exactly: CLEAN.
Otherwise return a short list, one line each:
  - [SEVERITY] <section> — <what is substantively wrong>. DECISION: <yes|no>.
```

### 6 — Converge or continue
- **Exit exam `CLEAN` AND floor passed → CONVERGED.** Go to **On convergence**.
- **Otherwise → next round.** Do not carry findings in context — the next round's fresh agents re-derive from the updated `WORKING` + the digest.
- **`M` reaches 20 without converging → STOP at cap.** Go to **On round cap**.

## State discipline (load-bearing)

The orchestrator keeps **nothing durable in its own context**:
- **`WORKING` on disk is the state.** Unresolved issues persist because they are still in the doc; the reviewer re-derives the canonical live list each round. Never filter a finding using memory of a prior round.
- **`## Open Decisions` in `WORKING` is the escalation memory** — an escalated decision lives there, so future reviewers skip it and it is not re-researched (the same mechanism as `NON_GOALS`). This is the one durable cross-round record, and it lives in the doc, not your context.
- **`DIGEST` is computed once and reused** every round and across re-runs (code is static).
- If compacted mid-loop, resume from disk: `M` = (count of `round-*.md` in `history/run-<RUN>/`) + 1; re-read paths via `improve_files.py paths <target>`; the digest and `## Open Decisions` are already on disk. Continue.

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
  4. **Approve:** `improve_files.py approve <target>` (+ `append-non-goal <target> "<text>"` per accepted proposed non-goal). Copies the finalized working copy over the original and archives the CHANGELOG (now carrying the `[resolution]` entries) into `history/run-<RUN>/`.
  5. **To verify the resolutions**, re-run `/mg-temp:spec-improve-auto <target>`: it cold-starts on the clean settled spec as the next run (history continues), and the reviewer now *reads* the settled content — no skip-lists — to confirm the new design holds.
- **Override an auto-decision** → the user names it by its `AD` number (e.g. `AD3`); map it to the underlying `### Dn:` block via the briefing, re-open it (Edit `WORKING` to back it out / adjust), and re-run.
- **Reject** → `improve_files.py reject <target>` (discards the working copy; the original is untouched — reject never reverts to the pristine `concept.original.md`).

## On round cap

Reaching the cap without a clean exit exam is a signal — usually genuine churn or a cluster of hard escalations. First clear any pending resume cron for this spec (`CronList`/`CronDelete`). Present an honest report: the last exit-exam's substantive findings; what kept churning (from `CHANGELOG`); the `## Open Decisions` list — run it through the **briefing writer** (above) so the escalations read cleanly; the scorecard. Then let the user **re-run** (another batch from `M+1`, e.g. after resolving a blocker), **approve the partial**, or **reject**.

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
- **Drive decisions, don't park them.** Real specs are never decision-complete, so a loop that only surfaces decisions can never converge. Every `DECISION: yes` finding gets a decide-agent that either **takes** it (writes a defensible resolution into the spec) or **escalates** it (frames it for the user). Convergence = the exit exam is clean *except* for the escalated Open Decisions.
- **Read once, branch (via digest).** The cited code is read a single time into `CODE-DIGEST.md`; every reviewer / decide / exit-exam agent reads that small digest instead of re-navigating the codebase (a ~5–10× cost lever). Agents fall back to opening a specific file only when the digest is silent. A genuine fork/shared-context primitive is not available on the Agent path, so the digest is the mechanism. The digest is **facts-only** — never enrich it with run-specific framing (e.g. "escalate this"), which would nudge re-escalation when it is reused across re-runs.
- **Model tiers.** Digest-reader + reviewer = **Sonnet** (heavy readers; a reviewer miss is self-correcting across rounds). Decide-agent + exit-exam + briefing writer = **Opus** (sharp judgment / user-facing prose; a bad auto-take is written into the spec and a false-CLEAN ends the loop — neither is self-correcting).
- **Decisions are working-quality during the loop; polished only at the hand-off.** Decide-agents write functional decisions (accuracy over prose); the reviewer and exit exam read the code and don't need polish. A single **briefing writer** produces the product-altitude prose once, when the run surfaces to the user (convergence or round cap) — keeping the per-round path lean and prose-writing out of the main loop's context. The concept's own `### Dn:` decision text stays implementer-facing, per the template.
- **Escalation safety, without a ledger.** Blast radius is judged by the decide-agent, not computed. Mitigations: the decide-agent is Opus; the working copy is the safety net (original untouched until approve); and every auto-take is in the briefing and the changelog — visible and reversible, never silently locked in.
- **`## Open Decisions` is loop-owned and lives in the working copy.** It is the escalation record and the reviewers' skip-list (like non-goals). On approval the user resolves it; it is not meant to ship unresolved.
- **Asymmetric bars.** The Step-1 reviewer is deliberately harsh and wide; the Step-5 exit exam holds a high, substantive-only bar. That asymmetry is what lets the loop converge when substantive issues (and their decisions) are handled, even if a harsh reviewer could always find one more nitpick.
- **The working copy is the safety net and the only state.** The orchestrator holds no durable round state; it re-reads from disk and is resilient to mid-loop compaction.
- **Usage-limit gate + self-scheduled resume.** Round step 0 reads the real Claude Code `/usage` (cost-free) and **pauses** the run when session > 75% or weekly > 90%, scheduling its own `--resume` at the binding window's reset via a one-shot `CronCreate` (session-only — it needs this session to stay alive, which a persistent terminal/multiplexer session provides). `--force` grants exactly one over-threshold round (via the `FORCE_MARKER` token), then the loop pauses again. Whenever the loop ends for any *other* reason — convergence, round cap, approve, reject — clear any pending resume cron for this spec (`CronList`/`CronDelete`) so a stale resume can't fire.
</important_notes>
