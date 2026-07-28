# Create Milestone

---
name: mg:spec-create-milestone
description: Project a frozen concept spec into a GSD milestone — PROJECT.md section, gated REQUIREMENTS.md with Dx traceability, and a coverage-enforced ROADMAP.md, without eliciting or re-deriving scope
argument-hint: "<version> <spec-path>"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

<objective>
Project a frozen, code-grounded concept spec into GSD-native milestone artifacts: a `PROJECT.md` current-milestone section, a gated `REQUIREMENTS.md` (with a net-new `## Spec Traceability` mapping every requirement to a decision `Dx` or a gate-approved research finding `SV-n`), then a coverage-enforced `ROADMAP.md`/`STATE.md` written by the unchanged `gsd-roadmapper`. This is the milestone-level, spec-first sibling of `mg:spec-create-context` (`spec→phase :: spec→milestone`).

It **projects** the spec rather than eliciting requirements; it **keeps** a research pass but **re-aims it from discovery to spec-verification** (does each decision still hold against the code, and what did the spec miss?); and it adds a **faithfulness gate** so scope cannot drift silently. Output is GSD-native — no GSD patches. The command never edits the spec.

The deterministic checks are all run by `.claude/spec/scripts/milestone_checks.py`, never eyeballed in-context. This command orchestrates; that script decides.
</objective>

<context>
Arguments: $ARGUMENTS

Expected format: `<version> <spec-path>`

Examples:
- `v6.0 docs/work-queue/todo/point-in-time-l2/concept.md`
- `v6.1 docs/work-queue/todo/some-slug/concept.md`

Requirements template snapshot: `.claude/spec/references/requirements-template.snapshot`
Checks script: `.claude/spec/scripts/milestone_checks.py` — always invoked as `uv run .claude/spec/scripts/milestone_checks.py <subcommand> [args]` (the family's pinned interpreter prefix). GSD-side inputs live at fixed `.planning/` paths, so only `citations`/`check` take the spec path and `preflight` takes `<version>`.

This command requires GSD (`.claude/get-shit-done/`) — unlike its sibling `spec-create-context`, it shells `gsd-tools.cjs` and spawns GSD agents.
</context>

<required_reading>
Read the GSD requirements template to understand the target `REQUIREMENTS.md` format and to run the drift check:
@./.claude/get-shit-done/templates/requirements.md
</required_reading>

<process>

The startup checks run in a **fixed order, all before anything in `.planning/` is written** (Stage 0). The order clears every fail-fast `ERROR` before the first interactive prompt, so the operator is never asked to confirm an overwrite and then hit an `ERROR` two checks later: arity → `preflight` → spec-content → template-drift → the one `preflight` confirm. An `ERROR` or Abort at any of steps 1–5 leaves `.planning/` byte-untouched.

## 1. Parse and validate arguments (arity)

Extract from `$ARGUMENTS`:
- **`<version>`** — the first token.
- **`<spec-path>`** — the remaining tokens joined as the path.

If either is missing, or extra positional arguments are present:
```
ERROR: <version> and <spec-path> are both required.

Usage: /mg:spec-create-milestone <version> <spec-path>

Example:
  /mg:spec-create-milestone v6.0 docs/work-queue/todo/point-in-time-l2/concept.md
```
Exit. (Arity necessarily precedes everything: `preflight` consumes `<version>`, the spec checks consume `<spec-path>`.)

## 2. Classify GSD-side state (preflight)

Run:
```bash
uv run .claude/spec/scripts/milestone_checks.py preflight <version>
```
It prints a JSON object with one named `verdict` plus the facts that drove it. **Map the verdict to the outcome below — do NOT re-derive the classification yourself.** A non-zero exit means an `ERROR` verdict.

| Verdict | Outcome |
|---------|---------|
| `missing-project` | `ERROR: .planning/PROJECT.md not found. Initialize GSD first: /gsd:new-project` → Exit. |
| `missing-gsd` | `ERROR: GSD not installed (.claude/get-shit-done/ missing). Install GSD, then re-run.` → Exit. |
| `bad-version` | `ERROR: Version must be dot-format vX.Y (e.g. v6.0). Got: <version>` → Exit. |
| `version-completed` | `ERROR: Milestone <version> is already recorded in MILESTONES.md. Re-running a completed milestone would corrupt bookkeeping.` → Exit. |
| `live-phase-current` | `ERROR: ROADMAP.md already has live phases for the current milestone <version>.` Then name the three recovery paths: `/mg:spec-gsd-phases` (add phases to a genuinely open milestone); `/gsd:complete-milestone` (close it first); or — if you know ROADMAP.md is the unapproved leftover of a crashed run — delete `.planning/ROADMAP.md` by hand and re-run as a pre-roadmap resume (nothing durable is lost; history persists in MILESTONES.md + `.planning/milestones/`). This command never deletes it for you. → Exit. |
| `open-other-milestone` | `ERROR: A previous milestone is still open (live REQUIREMENTS.md or live-phase ROADMAP.md) and <version> is not the current milestone. Close it first: /gsd:complete-milestone` → Exit. |
| `resume-pre-roadmap` | Proceed silently. Stage 0 idempotently rewrites the same section; the Stage-1 guard may offer Resume if `REQUIREMENTS.md` is snapshot-identical. |
| `abandoned-bookkeeping` | Defer to **step 5** (do not prompt yet — clear the fatal ERRORs and the drift gate first). |
| `clean` | Proceed silently. Stage 0 creates or rewrites the current-milestone section. |

If `preflight` itself prints a loud `Error:` (malformed/unparseable PROJECT.md or MILESTONES.md, or a garbled version token it names), surface that error verbatim and Exit — never proceed.

## 3. Validate spec content

Three spec `ERROR`s, independent of `preflight`. All are pre-mutation reads.

Read `<spec-path>`. If it does not exist or is empty:
```
ERROR: Spec file not found or empty: <spec-path>
```
Exit.

Grep the spec for `### Dn:` decision headings under `## Design Decisions`. If none exist:
```
ERROR: Spec has no D1..Dn decision blocks. This command consumes spec-family output.
Run /mg:spec-draft then /mg:spec-improve first.
```
Exit. (Genuinely unstructured docs have the `plan-phase --prd` path at phase level.)

Validate the citation contract (D8):
```bash
uv run .claude/spec/scripts/milestone_checks.py citations <spec-path>
```
On non-zero exit, print the named violation, then:
```
ERROR: Spec fails the citation contract (D8): <violation>.
Every top-level bullet under `### What gets built` must cite ≥1 existing Dx, e.g. `(D3)` or `(D3, D5)`.
Run /mg:spec-improve <spec-path> to add the missing citations.
```
Exit. (This also covers a missing or bullet-less `### What gets built` section — `citations` never passes vacuously.)

## 4. Template compatibility check (drift guard)

Verify the GSD requirements template hasn't changed since this command was last updated. This is the first interactive prompt.

1. Read the stored snapshot at `.claude/spec/references/requirements-template.snapshot`.
2. Read the live template at `.claude/get-shit-done/templates/requirements.md` (already loaded via required_reading).
3. Compare **only the `<template>` and `<guidelines>` blocks**. Ignore `<evolution>` and `<example>` — cosmetic example/evolution edits must not fire drift.

**If the compared blocks are identical:**
```
Template check: compatible.
```
Proceed to step 5.

**If different:** analyze the differences (sections renamed? new required subsections? removed sections?) and assess whether the Stage-1 projection headings (step 7) still hold. Then AskUserQuestion:
- header: "Template drift"
- question: "GSD's requirements template has changed since mg:spec-create-milestone was last updated. {summary of what changed and whether the projection is still compatible}. How should I proceed?"
- options:
  - "Continue anyway" — "Proceed using the live template as guidance. This warning appears on every run until the command is updated in mg-cc-tools and reinstalled."
  - "Abort" — "Stop. I'll update the command in mg-cc-tools first."

**If "Continue anyway":** proceed to step 5. Do **not** update the snapshot — it persists until the command source is updated and reinstalled.

**If "Abort":**
```
Aborted. Update the snapshot and command in mg-cc-tools, then reinstall:

  cd <mg-cc-tools>
  # Update spec/references/requirements-template.snapshot with the new template
  # Review spec/commands/spec-create-milestone.md
  ./spec/install.sh --project <this-project>
```
Exit with `.planning/` untouched.

## 5. Abandoned-bookkeeping confirm

Only if step 2's verdict was `abandoned-bookkeeping` (otherwise skip silently). All fatal `ERROR`s and the drift gate have now cleared. AskUserQuestion:
- header: "Abandoned bookkeeping"
- question: "PROJECT.md's Current Milestone names `{abandoned version}`, which is neither `<version>` nor a completed milestone in MILESTONES.md — it looks like a previous milestone-start that never finished. Overwrite it with `<version>` projected fresh from the spec?"
- options:
  - "Continue — overwrite" — "Rewrite the Current Milestone section to name <version>, projected from the spec. The abandoned version's name, goal, and target features are discarded, not merged."
  - "Abort" — "Stop. `.planning/` stays untouched."

On **Continue**, proceed to Stage 0. On **Abort**, Exit pre-mutation.

## 6. Stage 0 — Milestone bookkeeping (PROJECT.md + STATE.md)

Everything from here writes to `.planning/`. Mirror `new-milestone` steps 4–7. The ordering is load-bearing: Stage 4 passes `PROJECT.md` to the roadmapper, so it must describe **this** milestone before the roadmapper reads it.

**6a. Resolve config + models.**
```bash
INIT=$(node ".claude/get-shit-done/bin/gsd-tools.cjs" init new-milestone)
if [[ "$INIT" == @file:* ]]; then INIT=$(cat "${INIT#@file:}"); fi
```
Extract `researcher_model`, `roadmapper_model`, and `commit_docs` from the JSON. Inject `model="{researcher_model}"` / `model="{roadmapper_model}"` **verbatim** into the Stage-2/Stage-4 spawns — the value may be the literal string `"inherit"` (an opus profile) and must be passed through unchanged, exactly as `new-milestone` does. (`synthesizer_model` and `research_enabled` are unused: there is no synthesizer, and the Stage-2 verification pass always runs — it is faithfulness machinery, not discovery, so it deliberately ignores the persisted `workflow.research` toggle.)

**6b. Milestone name.** Derive from the spec's H1 title and confirm with the operator via AskUserQuestion (header "Milestone name", question "Name this milestone (from the spec title '{H1}')?", options: 1–2 slug-derived suggestions).

**6c. Update PROJECT.md.** Create-or-rewrite the `## Current Milestone: v[X.Y] [Name]` section (the post-completion evolution review may have removed or renamed it — create it if absent). Goal + target features are projected from the spec's Problem/Solution, matching `new-milestone` step 4:
```markdown
## Current Milestone: v[X.Y] [Name]

**Goal:** [one sentence from the spec]

**Target features:**
- [from the spec's Solution]
- ...
```
Also refresh the `Active requirements` section and the `Last updated` footer — a stale Active-requirements block still describing the previous milestone is exactly the residue this ordering exists to prevent.

**6d. Reset STATE.md** to "defining requirements", keeping the Accumulated Context section (`new-milestone` step 5's exact behavior):
```markdown
## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: [today] — Milestone v[X.Y] started
```

**6e. MILESTONE-CONTEXT.md disposition** (step-6 mirror, made visible). If `.planning/MILESTONE-CONTEXT.md` exists, AskUserQuestion (this command never reads it — the spec is the source — so do not auto-delete):
- header: "Milestone context"
- question: "A leftover .planning/MILESTONE-CONTEXT.md exists. This command never reads it. Delete it, or keep it for a later /gsd:new-milestone run?"
- options: "Delete — abandoned" / "Keep — for a later gsd:new-milestone"

Non-aborting either way.

**6f. Commit.**
```bash
node ".claude/get-shit-done/bin/gsd-tools.cjs" commit "docs: start milestone v[X.Y] [Name]" --files .planning/PROJECT.md .planning/STATE.md
```
`gsd-tools.cjs commit` self-checks `commit_docs` and skips when false — so "honoring commit_docs" at every commit point means exactly this: commit through `gsd-tools.cjs commit`, never raw git.

## 7. Stage 1 — Project the spec → REQUIREMENTS.md

**7a. Existing-file guard.** If `.planning/REQUIREMENTS.md` already exists (it belongs to the current milestone — `preflight` errored on any other), AskUserQuestion. Two options always: **Overwrite** / **Abort**. Offer a third, **Resume at Stage 4**, ONLY when:
```bash
uv run .claude/spec/scripts/milestone_checks.py snapshot --matches
```
exits 0 (a `.requirements.snapshot` exists and the live file is byte-identical to it — the gate-approved projection left by a crash). On **Resume**, skip Stages 1–3 and jump to Stage 4 (step 9). On **Overwrite**, continue 7b. On **Abort**, Exit.

**7b. Project the file.** Emit a GSD-native `REQUIREMENTS.md`. Section headings follow the live template verbatim: `## v1 Requirements` grouped by `### <Category>` with `- [ ] **[CAT]-NN**:` checkboxes; `## v2 Requirements` (`- **[CAT]-NN**:`, no checkbox); `## Out of Scope` (`| Feature | Reason |` table); `## Traceability` (seed an **empty placeholder** for Stage 5). Then the two net-new sections:
- **`## Spec Traceability`** — schema `| REQ | Source | Note |`, one row per REQ. Legal Source forms: decision-derived (`Dx` / `Dx, Dy`); amended (`Dx; SV-n (gate-approved)`); new-REQ-from-finding (`SV-n (gate-approved)`); waiver (`| — | Dx | waived: <reason> |`); deferred (`| — | Dx | deferred to v2 (CAT-NN): <reason> |`).
- **Scope-context note** — satisfied preconditions as a non-checkbox note (already-done work isn't re-scoped).

Apply the projection rules (faithful projection, so two implementers produce materially the same file):
- **Granularity:** default one REQ per `### What gets built` top-level bullet; the bullet's `(Dx)` citations become the row's Source. Merge bullets only when they state the same observable capability at different granularities. A `Dx` cited by no bullet projects to its own REQ if it demands observable work, else to a waiver row.
- **REQ-ID continuation:** `[CAT]-NN` continues from the highest existing number **per category** across `.planning/milestones/v*-REQUIREMENTS.md` archives (scan both v1 and v2 sections; the archive header carries no IDs). Categories with no prior REQs start at 01; everything starts at 01 when no archives exist.
- **Phrasing:** specific, testable, atomic, independent (GSD's `new-milestone` step 9 criteria); carry the spec's literal values (counts, totals, names) into REQ text **verbatim**.
- **Categories:** derived from the spec's own component/deliverable grouping (not a research `FEATURES.md`, which doesn't exist here). Reuse an archived category's prefix when the domain matches, else mint a new 3–5-char uppercase prefix.
- **v2 & Out of Scope sources:** `concept-NON-GOALS.md` + the spec's "What does NOT get built" → Out of Scope; the spec's deferred / resolved-as-later Open Items → v2 Requirements (v2 IDs draw from the same per-category continuation sequence as v1). Every v2 item MUST be anchored by a deferred-form waiver row naming it.

**7c. NON-GOALS discovery.** Glob `*-NON-GOALS.md` in the spec's directory. Read the exact-convention match (`<spec-basename>-NON-GOALS.md`) automatically. Present every other hit to the operator individually (AskUserQuestion confirm/skip per file). Zero hits → proceed, but the Stage-3 gate states "no NON-GOALS file found" explicitly (a missing Out-of-Scope source is a visible fact, never a silent drop). Also follow local markdown links inside the spec up to a **≤5** budget — but **linked docs are context, never scope**: they inform milestone naming, REQ phrasing, and gate presentation only. Requirements, waivers, and Source entries derive solely from the spec's `D1..Dn`, its cited `### What gets built` bullets, and gate-approved `SV-n` findings.

**7d. Propose waiver/deferred rows** for decisions that legitimately project to zero requirements (pure constraints, process/tooling decisions) or v2-only deferrals, so the gate can open (`check` fails while any `Dx` is uncovered; Approve is only offered once it passes). The operator adjusts or vetoes each at the Stage-3 gate. Then self-verify:
```bash
uv run .claude/spec/scripts/milestone_checks.py check <spec-path>
```

## 8. Stage 2 — Context-aware verification, then Stage 3 — Faithfulness gate

**8a. Record the research manifest** (exactly once, before the first spawn — never on re-spawns):
```bash
uv run .claude/spec/scripts/milestone_checks.py research-pre
```

**8b. Stale-file guard.** Delete any pre-existing `.planning/research/spec-verification.md` (a leftover from an earlier run would present stale findings as fresh).

**8c. Spawn the researcher** (reuse `gsd-project-researcher` unchanged; `model="{researcher_model}"`) with a spec-seeded, verify-only prompt — NOT the discovery dimensions:

```
Task(subagent_type="gsd-project-researcher", model="{researcher_model}", description="Spec verification", prompt="
<research_type>Spec verification — audit a frozen concept spec's decisions against the current codebase.</research_type>

<milestone_context>
SPEC-DRIVEN MILESTONE. A frozen, code-grounded concept spec is the source of scope — it is NOT to be re-discovered. Your job is verification, NOT ecosystem/feasibility discovery: for each decision Dx in the spec, confirm it still holds against the current code, and surface gaps, stale assumptions, and missing constraints the spec omitted. Do NOT answer 'can we build X' (feasibility) and do NOT survey external libraries — audit the frozen decisions against THIS repo's code.
</milestone_context>

<question>For each Dx in the spec, does it still hold against the current code? What did the spec miss (gaps, stale assumptions, missing constraints)?</question>

<files_to_read>
- {spec-path} (the frozen concept spec: D1..Dn + Scope)
- {each confirmed NON-GOALS file} (explicit scope exclusions — do not flag issues inside a listed non-goal)
- .planning/REQUIREMENTS.md (the just-projected requirements this run produced)
- .planning/codebase/ (codebase map, if present)
- {the concrete source dirs the spec's decisions touch}
</files_to_read>

<output>
Write to: .planning/research/spec-verification.md
Emit ONLY that file. Do NOT write SUMMARY.md, STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md, FEASIBILITY.md, or any other file — this is a verification pass, not domain discovery.

The file MUST be a single markdown findings table, one finding per row, with EXACTLY this header and column order:

| id | decision-ref | kind | what | suggested-addition | severity |

- id: sequential SV-1, SV-2, … SV-n
- decision-ref: a Dx or a REQ id, or `—` for a spec-wide finding
- kind: one of gap | stale | missing-constraint
- severity: one of critical | major | minor

Zero findings = the header row and no data rows. Do not add prose outside the table.
</output>
")
```

**8d. Run the janitor** after every researcher return (removes stray discovery files by set-difference; idempotent):
```bash
uv run .claude/spec/scripts/milestone_checks.py research-post
```

**8e. Findings-file recovery.** If `check` (step 8f) reports an unparseable `spec-verification.md`, re-spawn the researcher with the parse error and the pinned table contract as revision context. After **2** failed re-spawns for the same parse failure, hand the file to the operator to hand-edit into contract shape and re-run `check` (the operator is the gate's approval authority, so hand-edits open no channel the gate doesn't grant).

**8f. Stage-3 faithfulness gate (single scope approval).** Run:
```bash
uv run .claude/spec/scripts/milestone_checks.py check <spec-path>
```
`check` verifies completeness (every `Dx` → ≥1 Source or waiver), no-drift (every Source is a legal form), REQ↔row bidirectionality, v2-anchoring, SV-citation existence, and REQ-ID collision. **Approve is offered ONLY once `check` passes.** While it fails, present the named violations with **Edit** / **Reject** only — there is no approve-with-known-violations path.

Present the gate for a single scope approval (the roadmap gets its own approval in Stage 4):
- **Completeness:** every spec `Dx` → ≥1 requirement or an operator-approved waiver row.
- **No drift:** every requirement → a `Dx`, or an explicitly flagged Stage-2 finding the operator accepts/rejects item-by-item. An accepted finding that introduces a **new** REQ records Source `SV-n (gate-approved)`; one that **amends** an existing decision-derived REQ (the `GRANT` shape) keeps that REQ's row and appends `; SV-n (gate-approved)` to its Source. Either way the Note column carries a one-line summary. NG3 stands: the spec file is never edited.
- **Zero-REQ decisions** use waiver rows, not filler REQs; v2-deferred scope uses the deferred variant.
- Stage-2 findings are the **only** source of beyond-spec scope.

AskUserQuestion once `check` passes: **Approve** / **Edit** / **Reject**.
- **Approve** →
  ```bash
  node ".claude/get-shit-done/bin/gsd-tools.cjs" commit "docs: define milestone v[X.Y] requirements" --files .planning/REQUIREMENTS.md .planning/research/spec-verification.md
  uv run .claude/spec/scripts/milestone_checks.py snapshot
  ```
  (The verification file must be as durable as the traceability rows citing its `SV-n` ids.) Proceed to Stage 4.
- **Edit** → apply the operator's edits to `REQUIREMENTS.md` (including `## Spec Traceability`), or — for findings-file violations — to `.planning/research/spec-verification.md`; re-run `check`; re-present. Loop until Approve/Reject.
- **Reject** →
  ```bash
  uv run .claude/spec/scripts/milestone_checks.py snapshot --clear
  ```
  Leave `REQUIREMENTS.md` uncommitted for inspection; the Stage-0 commit stands. The operator revises the spec upstream and re-runs. Exit.

## 9. Stage 4 — Roadmap (reuse gsd-roadmapper, unchanged)

**9a. Compute the start number** (same value `preflight` used — computed once, pre-mutation; re-running is idempotent):
```bash
uv run .claude/spec/scripts/milestone_checks.py phase-start
```

**9b. Spawn the roadmapper** (agent unchanged; `model="{roadmapper_model}"`) with the explicit input set `new-milestone` gives it, **minus `research/SUMMARY.md`**:

```
Task(subagent_type="gsd-roadmapper", model="{roadmapper_model}", description="Create roadmap", prompt="
<planning_context>
<files_to_read>
- .planning/PROJECT.md
- .planning/REQUIREMENTS.md
- .planning/config.json
- .planning/MILESTONES.md (if it exists)
</files_to_read>
Do NOT read .planning/research/ or any file within it. There is no SUMMARY.md input for this milestone — the requirements are already a gated, faithful projection of a frozen spec. Reading research would re-admit the discovery scope this workflow exists to exclude.
</planning_context>

<instructions>
Create the roadmap for milestone v[X.Y]:
1. Start phase numbering from [N].
2. Derive phases from THIS milestone's REQUIREMENTS.md requirements only.
3. Map every v1 requirement to exactly one phase; validate 100% coverage.
4. Derive 2-5 observable success criteria per phase.
5. Write ONLY .planning/ROADMAP.md and .planning/STATE.md. Do NOT write or edit .planning/REQUIREMENTS.md — its traceability table is filled by a script after you return.
6. Requirements are FROZEN. Gap resolution must NEVER add, remove, demote-to-v2, or otherwise descope a requirement. If any requirement cannot be placed, return `## ROADMAP BLOCKED` and let the operator decide — do NOT resolve it by editing REQUIREMENTS.md.
7. Return `## ROADMAP CREATED` (or `## ROADMAP BLOCKED`) with a summary.

Write files first, then return.
</instructions>
")
```

**9c. After EVERY roadmapper return: restore, then cross-check** (script-run, not eyeballed):
```bash
uv run .claude/spec/scripts/milestone_checks.py restore
uv run .claude/spec/scripts/milestone_checks.py coverage
```
`restore` runs unconditionally — it rewrites `REQUIREMENTS.md` byte-exact from the gate-approval snapshot, erasing any roadmapper edit to that file by construction (so a roadmapper edit never triggers a re-spawn). `coverage` then confirms the bidirectional REQ↔phase mapping against the snapshot's gated set.

Return handling (mirrors `new-milestone` step 10):
- `## ROADMAP BLOCKED` → present the blocker, work with the operator, re-spawn.
- `## ROADMAP CREATED` → run the restore→coverage sequence above.
- A **`coverage` violation** (REQ unmapped, double-mapped, or invented) → re-spawn the roadmapper with revision context naming it (its `## ROADMAP REVISED` flow).
- **Bounded:** after **2** failed re-spawns for the same violation, present it to the operator: hand-edit `ROADMAP.md` and continue (the hand-edited file re-enters the same restore→coverage sequence before any approval), re-spawn once more with their notes, or abort (an abort leaves the Stage-0/Stage-3 commits and the unapproved `ROADMAP.md` on disk — the crashed-run state whose remedy the `live-phase-current` ERROR names).

The restore→coverage sequence re-runs after **every** roadmapper return before any approval prompt.

**9d. Roadmap approval.** Once restore→coverage passes, present the roadmap (inline phase table, mirroring `new-milestone`) via AskUserQuestion: **Approve** / **Adjust phases** / **Review full file**. "Adjust" → re-spawn with revision notes, looping (sequence included) until approved. Nothing is committed until approval.

## 10. Stage 5 — Fill traceability + commit roadmap artifacts

`PROJECT.md`/`STATE.md` were committed in Stage 0, and the roadmapper wrote `STATE.md` fresh in Stage 4 — **do not rewrite STATE.md here.** First fill the table, then commit:
```bash
uv run .claude/spec/scripts/milestone_checks.py traceability
node ".claude/get-shit-done/bin/gsd-tools.cjs" commit "docs: create milestone v[X.Y] roadmap" --files .planning/ROADMAP.md .planning/STATE.md .planning/REQUIREMENTS.md
```
`traceability` fills the `## Traceability` placeholder from the approved `ROADMAP.md` (one `| REQ | Phase N | Pending |` row per mapping + the `**Coverage:**` summary) — the roadmapper never writes the table, so `REQUIREMENTS.md` and `ROADMAP.md` cannot disagree. The fill sits here (not Stage 4) so the live file stays byte-identical to the snapshot throughout the approval loop, preserving Stage 1's Resume detection.

## 11. Stage 6 — Handoff

Derive `{first}`/`{last}` from the approved `ROADMAP.md` phase numbers (the coverage re-check already parsed the roadmapper-assigned numbers — the printed range is the actual continued numbering, never 1-based). Print:

```
## Next Steps

  /mg:spec-prepare-context {first}-{last} {spec-path}    ← split the spec into per-phase files
  /mg:spec-create-context {N} {per-phase file}           ← per phase: project the split into CONTEXT.md
  /mg:plan-phase {first}                                 ← then plan as usual

Caveat: the faithfulness guarantee ends here. On a spec-projected milestone, treat any
plan-phase "+N added" requirement output as beyond-spec scope to review against the spec.
To flag the row-less checkboxes such additions leave, re-run:
  uv run .claude/spec/scripts/milestone_checks.py check {spec-path}
```

</process>

<important_notes>
- **`## Spec Traceability` is net-new** and kept separate from GSD's own `## Traceability` (REQ→Phase): the former is source→requirement (`Dx`/`SV-n`), the latter is script-filled from `ROADMAP.md` in Stage 5.
- **The roadmapper is barred from `REQUIREMENTS.md`.** Its role doc expects to update the `## Traceability` table in place; here it is instructed to write only `ROADMAP.md` + `STATE.md`, and the unconditional whole-file `restore` after every return erases any write by construction (D5) — so tampering never survives to need policing.
- **Beyond-spec scope enters ONLY via a gate-approved Stage-2 `SV-n` finding** (D3). There is no `--also` freeform input; the spec is the sole scope source otherwise.
- **All deterministic checks are `milestone_checks.py`, never eyeballed.** The command maps verdicts/violations to text; it never re-derives the classification in-context.
- **The snapshot at `.claude/spec/references/requirements-template.snapshot` is not updated at runtime on drift** — it persists until the command source is updated and reinstalled, so the drift warning keeps appearing until then.
- **This command requires GSD** (`gsd-tools.cjs` + the agents) — unlike its sibling `spec-create-context`.
- **Always invoke the script as `uv run .claude/spec/scripts/milestone_checks.py <sub>`** — the family's pinned interpreter prefix.
- **The Stage-2 verification pass always runs**, deliberately ignoring the persisted `workflow.research` toggle: it is faithfulness machinery (the gate's `SV-n` findings reference), not discovery research.
</important_notes>
