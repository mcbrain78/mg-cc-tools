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
   - **On success (exit 0):** capture the emitted resolved-paths JSON. Store it as `PATHS_JSON`. If `backup_created` is true, report: `Backed up original to <original_backup>`.
   - **On guard-fail (exit 1):** an in-progress working copy from a prior session exists (the D7 guard). Do **not** overwrite it. Run the read-only `uv run {MG_INSTALL_SCRIPTS_DIR}/improve_files.py paths <target-file-path>`, surface the leftover state, then use **AskUserQuestion** for the binary choice:
     - **Resume** — continue with the existing working copy. Use the `paths` JSON as `PATHS_JSON`.
     - **Discard and restart** — run `improve_files.py init <target-file-path> --fresh`, then use its JSON.

     This AskUserQuestion is the **only** picker before convergence. The loop is otherwise autonomous.

   Bind from `PATHS_JSON`:
   - `WORKING` = `auto_improve` (every edit lands here)
   - `NON_GOALS` = `non_goals` (may not exist yet; `non_goals_exists` tells you)
   - `CHANGELOG` = `changelog`
   - `RUN` = `next_run`
   - `HISTORY` = `history_dir`

   Also define, both siblings of `WORKING` (derive by string, do not create yet):
   - `DIGEST` = `<dir-of-WORKING>/CODE-DIGEST.md` — the shared code facts (Step 0)
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
flag them (explicit scope exclusions are fine); also flag as a MINOR fix any `### Dn:` block that does not open with a plain-language **Context:** line (situation + problem in product terms, no code identifiers) — a decision a reader cannot follow without the code in front of them fails the readability bar; (7) a concrete simpler
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
        new `### Dn:` decision block, a corrected premise, a resolved open item.
        Contracts/prose, never implementation code. A `### Dn:` block MUST open
        with a **Context:** line — the situation and the problem it resolves, in
        plain product language with NO code identifiers (those go in Why) — then
        **Choice** / **Why** / **Alternatives rejected** as in the template, so a
        reviewer can judge it without reverse-engineering it from the answer.>

ESCALATE — if the answer is genuinely ambiguous, high-stakes, wide-blast-radius,
or would reverse intent/a non-goal. Frame it as a decision memo a reader with
high-level product knowledge (not the code) can act on: plain language, with
code specifics only in a clearly-marked tail. Return:
  VERDICT: ESCALATE
  SITUATION: <the relevant state of the world in plain product terms, 1-2 sentences>
  PROBLEM: <the tension that forces a choice, and why you cannot just take it
           (genuinely ambiguous / high-stakes / would reverse intent), 1-2 sentences>
  OPTIONS: <the REAL options — usually 2-4; do NOT pad to a fixed count. Open with
           one line naming the axis they trade on. Label each option with a
           sequential lowercase letter — **a**, **b**, **c**, … — then a short
           name, then its pros and its cons. The letters give the user something
           short to type back. Unavoidable code specifics go in a trailing
           "(impl: …)" clause, never in the framing.>
  RECOMMENDATION: <your lean named by its letter (e.g. "b") + confidence (e.g.
                  "moderate"), the one reason it wins, and what would flip you to
                  another option>
  GOVERNS: <the spec sections/decisions this choice controls, so review skips them
           until it is resolved — e.g. "the WASO solution section, D1, D8, D10">

Default to TAKE when you can defend it; escalate only what truly needs the human.
```

For each result:
- **TAKE** → apply `EDIT` to `WORKING` (Read then Edit), and log: `append-changelog <target> --run <RUN> --round <M> --kind decision-take "<one-line: what was decided>"`.
- **ESCALATE** → append the framed decision to the `## Open Decisions` section of `WORKING` (create the section once, near the end, before `## Verification` if present, else at end) as an `### ODn — <title>` entry. Render the escalation's own beats as a decision memo: **Situation** → **Problem** → **Options** (the axis line, then each lettered option — **a**, **b**, **c**, … — with its pros/cons) → **Recommendation** (naming its pick by letter), closing with a **Governs (skip in review until resolved):** line carrying its `GOVERNS` list. Product-altitude prose; code specifics only in the `(impl: …)` tails. This makes it surfaced-to-user and, being in the doc — including the Governs list — invisible to the sections future reviewers would otherwise re-flag.

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

## On convergence

Present a **briefing**, in order. Write every decision at product altitude — a reader with high-level product knowledge, not the code, must be able to follow it; keep code identifiers out of the summary lines.
1. **Auto-decisions taken this run** — from `CHANGELOG` (`[decision-take]` entries). Give each a **compact** memo (~3-4 lines): one line of situation + problem, the option chosen and the single reason it won, and the main rejected alternative. Point at the `### Dn:` block for the full reasoning. These were taken autonomously — invite override.
2. **Open Decisions** — read the `## Open Decisions` section of `WORKING` and present each in **full**: situation → problem → the real options with their tradeoffs → your recommendation. The user has to act on these, so they earn the length — do not compress them.
3. **Mechanical fixes** — summarize the run's `[fix]` entries.
4. **Scorecard** (see below).

Then the approval flow (fixes approved independently of non-goals, as `spec-improve`):
- **Accept** → `improve_files.py approve <target>` (+ `append-non-goal <target> "<text>"` per accepted proposed non-goal). The user then typically resolves the Open Decisions — either editing them into the spec directly, or answering here by option letter (e.g. `OD1 = b, OD2 = a`) so you apply them, then optionally re-running for another pass. Acceptance ends the session.
- **Override an auto-decision** → the user says which; re-open it (Edit `WORKING` to back it out / adjust) and re-run.
- **Reject** → `improve_files.py reject <target>` (discards the working copy; original untouched).

## On round cap

Reaching the cap without a clean exit exam is a signal — usually genuine churn or a cluster of hard escalations. Present an honest report: the last exit-exam's substantive findings; what kept churning (from `CHANGELOG`); the `## Open Decisions` list; the scorecard. Then let the user **re-run** (another batch from `M+1`, e.g. after resolving a blocker), **approve the partial**, or **reject**.

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
- **Read once, branch (via digest).** The cited code is read a single time into `CODE-DIGEST.md`; every reviewer / decide / exit-exam agent reads that small digest instead of re-navigating the codebase (a ~5–10× cost lever). Agents fall back to opening a specific file only when the digest is silent. A genuine fork/shared-context primitive is not available on the Agent path, so the digest is the mechanism.
- **Model tiers.** Digest-reader + reviewer = **Sonnet** (heavy readers; a reviewer miss is self-correcting across rounds). Decide-agent + exit-exam = **Opus** (sharp; a bad auto-take is written into the spec, and a false-CLEAN ends the loop — neither is self-correcting).
- **Escalation safety, without a ledger.** Blast radius is judged by the decide-agent, not computed. Mitigations: the decide-agent is Opus; the working copy is the safety net (original untouched until approve); and every auto-take is in the briefing and the changelog — visible and reversible, never silently locked in.
- **`## Open Decisions` is loop-owned and lives in the working copy.** It is the escalation record and the reviewers' skip-list (like non-goals). On approval the user resolves it; it is not meant to ship unresolved.
- **Asymmetric bars.** The Step-1 reviewer is deliberately harsh and wide; the Step-5 exit exam holds a high, substantive-only bar. That asymmetry is what lets the loop converge when substantive issues (and their decisions) are handled, even if a harsh reviewer could always find one more nitpick.
- **The working copy is the safety net and the only state.** The orchestrator holds no durable round state; it re-reads from disk and is resilient to mid-loop compaction.
</important_notes>
