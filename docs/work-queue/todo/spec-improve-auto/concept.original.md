# spec-improve-auto: Workflow-Driven Autonomous Spec Refinement

## Situation

The spec family pipeline runs `mg:spec-draft` → `mg:spec-improve` → `mg:spec-create-milestone`. The middle step, `spec-improve` (`spec/commands/spec-improve.md`), refines a concept spec through rounds of fresh-eyes subagent review:

- One reviewer subagent per round, carrying 10 review dimensions in a single prompt (contradictions, missing pieces, assumptions, engineering calibration, examples↔text, decision quality, simpler alternatives, over-specification, verification coverage, citation discipline).
- Triage caps fixes at **5 per round**; remaining issues "surface in subsequent rounds."
- Every round ends in a hard stop: report → wait for user approval → user re-invokes for the next round.
- All modifications happen on a working copy (`concept-auto-improve.md`, managed by `spec/scripts/improve_files.py`); the original is untouched until explicit `approve`. A `concept-NON-GOALS.md` sidecar accumulates approved scope exclusions that suppress future reviewer flags.

In practice a spec takes **~7 rounds** to refine, each requiring manual re-invocation, and the session ends when the user judges the remaining findings too minor to continue — not when the tool decides it is done.

Relevant existing infrastructure:

- The Claude Code **Workflow tool**: deterministic JavaScript orchestration of subagents (`agent()`, `pipeline()`, `parallel()`, loops). No tool in this repo uses it yet.
- `spec/scripts/milestone_checks.py citations <spec-path>`: the only deterministic check that runs standalone against a working copy (D-block citation discipline; never a vacuous pass).
- In-repo precedents for the mechanics this concept needs: codebase-health's adversarial verify step ("the scanner is fallible; don't rubber-stamp"; "prefer false negatives" for fixes), auto-doc auditv2's convergence assessment (trend-based stop recommendation, "default to CONTINUE if unsure") and dismissed-entity memory (persistent lists preventing re-flagging).
- `improve_files.py init` **unconditionally overwrites** an existing working copy from the source (create-once backup, always-reset working copy).

## Problem

1. **Artificial serialization.** The 5-fix cap forces a spec with 15 mechanical findings into 3+ rounds even when nothing depends on anything. Each round costs a full human gate (report, approval, re-invocation) even when every fix is cosmetic-safe.

2. **No self-termination.** The reviewer is a relative grader: "be harsh, flag everything" plus a critical/major/minor scale with no external anchor means severity normalizes to whatever remains in the current spec. On a near-final spec, the worst remaining nit is that round's "major." The loop structurally never returns empty, so a human must judge "relatively major vs. actually done" and abort manually — the observed ~7-round pattern.

3. **Decisions surface as a drip, under-prepared.** Genuine decisions (intent/scope/architecture) arrive mixed into each round's batch and get discussed one round at a time, without dedicated research. Empirically these decision points are highly relevant and need real back-and-forth — but the current shape spreads that discussion across re-invocations instead of concentrating it.

4. **A pause-and-resume hazard.** Any flow that pauses for discussion and later re-runs `init` silently destroys unapproved fixes in the working copy (`improve_files.py` always resets it from the source). Today this is latent; an autonomous tool that brackets discussions with multiple runs makes it acute.

## Solution

### Overview

A new command `mg:spec-improve-auto` drives the refinement loop through the Workflow tool. One invocation alternates between **autonomous drain runs** (a deterministic workflow script fans out lens reviewers, dedups findings, passes them through an adversarial severity gate, applies every fix that survives, and loops until the gate goes dry) and **in-conversation decision discussions** (genuine intent/scope/architecture decisions come back as research-backed cards; the user and the main agent resolve them in prose; resolutions feed the next run as free-form directives). The loop terminates itself: convergence is "no auto-fixable finding survives the gate for two consecutive rounds and the deterministic checks pass," not "the reviewer found nothing" — which never happens.

The division of labor: subagents do what fresh eyes are good for (finding, researching, judging severity), the main conversation does what context is good for (weighing decisions with the user), and the workflow script does what determinism is good for (looping, counting votes, terminating). The existing safety net survives intact: all edits land on the working copy, the original changes only on explicit approve, and fixes and non-goals are approved independently.

### Command flow (outer loop)

The command .md orchestrates; the workflow script executes one drain run per invocation.

1. **Setup.** Parse target path; run `improve_files.py init <target>`. If a working copy already exists, `init` now fails loudly (D7) — the command surfaces the leftover state to the user instead of destroying it.
2. **Drain run.** Invoke `Workflow({scriptPath: <installed workflow>, args})`. Args carry the resolved file paths and, on later runs, the directives from the previous discussion.
3. **On return** the workflow reports one of three statuses:
   - `converged` — present the final report (changelog summary + scorecard); user approves/rejects fixes and proposed non-goals independently via `improve_files.py`, as in `spec-improve` today.
   - `blocked` — the drain is dry except for decisions. Present the decision cards, discuss them in prose in the conversation (dependency-ordered, one nuanced decision at a time — no pickers), collect resolutions as free-form directives, and invoke the workflow again.
   - `round-cap` — the drain did not converge within the cap. Present an honest non-convergence report (what kept churning); this is itself a signal the spec has a structural problem.
4. Repeat until a run exits `converged`.

Workflow return contract (interface):

```json
{
  "status": "converged | blocked | round-cap",
  "rounds": 3,
  "fixed": 14,
  "below_bar": 6,
  "cards": [
    {
      "id": "C1",
      "title": "…",
      "finding": "what the reviewer flagged",
      "research": "codebase context gathered for this decision",
      "options": [{"option": "…", "tradeoff": "…"}],
      "recommendation": "…",
      "blast_radius": ["## Solution/### …", "### D3"],
      "depends_on": []
    }
  ],
  "proposed_non_goals": ["…"]
}
```

Args contract for run N+1: the same paths object plus `"directives": ["free-form prose resolution or editorial instruction", …]`.

### Drain round (inner loop)

Each round inside the workflow:

1. **Deterministic floor.** Run `milestone_checks.py citations <working-copy>` and `spec_checks.py structure <working-copy>`. Failures are definitionally substantive — they bypass the gate and go straight to the fix queue.
2. **Fan-out.** Four lens reviewers in parallel (D3), each context-free, each reading the full working copy, the concept template, the NON-GOALS and IMPLEMENTER-NOTES sidecars, and any code the spec references:
   - **Holistic design** — contradictions, over/under-engineering, simpler whole-design alternative (#1, #4, #7)
   - **Implementability** — missing pieces, unstated assumptions (#2, #3)
   - **Decision quality** — open questions, thin decisions, deferred commitments (#6)
   - **Spec hygiene** — examples↔text, over-specification, verification coverage (#5, #8, #9)
3. **Merge.** One dedup agent partitions all findings by root cause under a complete-partition contract (every finding in exactly one group, no gaps, no duplicates — the auto-doc `group-findings` contract).
4. **Gate.** A panel of three perspective-diverse judges (D4, D5), each judging the full deduped list — perspectives: *builds-wrong-thing*, *implementer-blocked*, *scope-intent-drift*. A finding is **substantive** if ≥2 judges confirm it names a concrete implementation-time failure. Substantive findings are then classified: **auto-fixable** (no intent/scope/architecture change) or **needs-user** (permissive escalation — when in doubt, surface).
5. **Record below-bar.** Findings that fail the gate are appended to the IMPLEMENTER-NOTES sidecar via `improve_files.py append-note` (D6) — judged once, remembered, never re-litigated.
6. **Fix.** A single fixer agent applies all auto-fixable findings to the working copy and appends one changelog entry per fix (what changed, why, which finding) to the changelog sidecar.
7. **Terminate or loop.** Zero substantive auto-fixables this round → dry-round counter increments; any fix resets it. **Two consecutive dry rounds + deterministic floor passing = converged.** Dry but with accumulated needs-user findings = `blocked`: one researcher agent per card gathers codebase context, options, tradeoffs, a recommendation, and the blast radius (which spec sections the decision touches), so research reflects the fully drained spec. Round cap (6) = `round-cap`.

On a directive-carrying run, an **apply agent** executes the directives against the working copy first (logging changelog entries), then the drain rounds proceed as above — resolutions create new review surface and must be re-reviewed like anything else.

Cost shape: ~9 agents per round (4 reviewers + 1 merger + 3 judges + 1 fixer), plus one researcher per decision card at escalation.

### The two gates

The gates answer different questions and deliberately carry opposite default polarities (D5):

- **Termination gate (skeptical, default-refute).** Bar: *name the concrete failure at implementation time if this is not fixed* — the implementer builds the wrong thing, gets stuck, or must come back and ask. No nameable failure → below bar. This replaces the relative critical/major/minor scale with an absolute, falsifiable test that does not drift as the spec improves — which is what makes the loop self-terminating.
- **Escalation gate (permissive, default-surface).** Bar: *does resolving this change intent, scope, or architecture?* If plausibly yes, it becomes a decision card. Failure costs are asymmetric: a wrongly suppressed decision becomes an implementer's guess (the 5–10x cost this pipeline exists to prevent); a wrongly surfaced one costs minutes of conversation.

### Artifacts and state

All cross-round and cross-run state lives in files (D10); every agent is spawned context-free.

```
docs/work-queue/todo/{name}/
├── concept.md                        ← original; only touched by approve
├── concept.original.md               ← create-once backup (existing)
├── concept-auto-improve.md           ← working copy (existing)
├── concept-NON-GOALS.md              ← approved scope exclusions (existing)
├── concept-IMPLEMENTER-NOTES.md      ← below-bar findings, gate memory (new)
└── concept-CHANGELOG.md              ← per-fix audit trail (new)
```

- **IMPLEMENTER-NOTES** mirrors the NON-GOALS format (header + flat bullets). It is fed to the gate each round as prior-judgment memory (below-bar findings are not re-judged) and remains after approval as advisory input for the implementer. It is *not* consumed by `spec-create-milestone`.
- **CHANGELOG** is part of the working-copy family: created during the run, its path emitted by `init`, deleted by `approve`/`reject`. It is what makes the autonomous drain auditable — the user reviews *what changed and why* at the end instead of gating every round.
- `improve_files.py init` output JSON gains `implementer_notes`, `changelog`, and corresponding `*_exists` keys.

### Registration and installation

The command follows standard spec-family anatomy: `spec/commands/spec-improve-auto.md` added to the `COMMANDS` array, header comment, and invoke-echo block of `spec/install.sh`; listed in `spec-help.md`. The workflow script is a new artifact class: `spec/workflows/spec-improve-auto.js`, copied to `<target>/.claude/spec/workflows/` by a new install step, referenced from the command via a new `{MG_INSTALL_WORKFLOWS_DIR}` placeholder (one new sed pair + path variable). New Python scripts drop into `spec/scripts/` (auto-globbed, no install.sh change).

## Design Decisions

### D1: Separate command; `spec-improve` stays untouched

**Choice:** Build `mg:spec-improve-auto` as a new command. `mg:spec-improve` keeps its current behavior as the manual path.

**Why:** The 5-cap and per-round human gate exist on purpose for the manual path — cheap, controllable, appropriate for small specs. The autonomous variant has a different cost/control profile; forcing both into one command means mode flags and conditional behavior in an LLM-interpreted .md.

**Alternatives rejected:** Replacing `spec-improve` (removes the cheap manual option); one command that escalates to the workflow when finding volume warrants (adds a volume-estimation step and conditional orchestration for little gain — the user knows which mode they want).

### D2: Workflow tool for orchestration; JS carries control flow and prompts only

**Choice:** The drain loop is a Workflow-tool script (plain JavaScript — the only language the tool executes). The JS contains *zero business logic*: agent prompts, fan-out structure, vote counting, loop counters. Every deterministic computation lives in Python under `spec/scripts/`, invoked by the workflow's agents via Bash.

**Why:** The self-driving property depends on the loop being code, not LLM-followed instructions — round discipline, vote thresholds, and termination must not drift over many autonomous rounds. Only the Workflow tool provides deterministic multi-agent control flow; Python scripts cannot spawn agents. Keeping the JS thin preserves this repo's markdown/Python separation rule with one added clause: JS = control flow + prompts.

**Alternatives rejected:** Agent-tool orchestration from the command .md (the codebase-health pattern) — zero JS and full repo precedent, but the loop itself becomes LLM-interpreted instructions, reintroducing exactly the drift this concept eliminates.

### D3: Fan-out as four lens reviewers plus a deterministic floor

**Choice:** Per round: four parallel context-free reviewers (holistic design / implementability / decision quality / spec hygiene, covering the 9 LLM-judged dimensions), plus deterministic script checks for what needs no judgment.

**Why:** The 10 dimensions split by the kind of attention they need — whole-document step-back, implementer's gaps, per-D-block scrutiny, local hygiene. A spec is ~200 lines, so every reviewer reads all of it; lenses direct attention rather than partition input. The holistic lens exists because contradictions (#1) and the simpler-alternative check (#7) vanish if every reviewer sees only one concern — #7 is often the single highest-value finding.

**Alternatives rejected:** One agent per dimension (codebase-health runs 14, but over a whole codebase; overkill for one small file); the current single 10-dimension reviewer (depth per dimension suffers, single perspective).

### D4: Termination = adversarial gate going dry, not reviewer silence

**Choice:** Finding and judging are separated. Reviewers keep "flag everything." A batched panel of three perspective-diverse judges rules on the full deduped list each round; ≥2 confirmations = substantive. Converged = two consecutive rounds with zero substantive auto-fixable findings AND the deterministic floor passing. Round cap: 6, then an honest non-convergence report.

**Why:** Reviewers are relative graders — severity normalizes to the current spec's distribution, so "reviewer finds nothing" never fires. The judges apply an absolute falsifiable bar instead (see D5). Batching the panel (3 calls/round judging all findings) instead of per-finding refuter trios (15–60 calls/round) keeps diversity and adds cross-finding context at a fraction of the cost. Two dry rounds guard against premature convergence (auto-doc's "default to CONTINUE if unsure"); the final human approve means a wrongly-dropped finding costs a later round, not a bad merge.

**Alternatives rejected:** Loop-until-reviewer-silence (structurally never terminates); per-finding refuter trios (cost without added signal — the panel already diversifies perspective); trend-based stop like auto-doc's assess-convergence alone (advisory trends still need a human to call it; the falsifiable bar decides per-finding).

### D5: Two gates with opposite default polarities

**Choice:** The termination gate is skeptical (default-refute; bar: name the concrete implementation-time failure). The escalation gate is permissive (default-surface; bar: plausibly changes intent, scope, or architecture).

**Why:** They answer different questions with asymmetric failure costs. Suppressing a real decision silently converts it into an implementer's guess — the 5–10x downstream cost. Surfacing a borderline one costs minutes. Meanwhile the termination gate must be strict or the loop never ends — the whole point. Empirically (user experience across spec-improve sessions), surfaced decisions have been consistently relevant, so the escalation filter should err open.

**Alternatives rejected:** One gate for both (forces a single bar that is either too strict for escalation or too loose for termination).

### D6: Below-bar findings persist in an IMPLEMENTER-NOTES sidecar

**Choice:** Gate-refuted findings are appended once to `concept-IMPLEMENTER-NOTES.md` (NON-GOALS-style format) and fed back to the gate as prior-judgment memory. The file survives approval as advisory input for the implementer.

**Why:** Without memory, the same minor finding resurfaces every round and burns gate budget (the auto-doc dismissed-entities problem, solved the same way: persistent judged-once lists). A sidecar keeps the frozen spec clean and mirrors the established NON-GOALS convention.

**Alternatives rejected:** Open Items section (leaks into v2-requirements projection — `spec-create-milestone` routes deferred Open Items there); NON-GOALS (wrong semantics — those suppress reviewer flags for *intentional exclusions*, not below-bar observations); an in-spec `## Implementer Notes` section (breaks template symmetry, visible to future reviewers as an unexpected section); report-only (lost after the session).

### D7: `improve_files.py` hardening — init guard (breaking) and sidecar lifecycle

**Choice:** `init` refuses to overwrite an existing working copy (exit 1, loud message); a new `--fresh` flag forces the old reset behavior. New `append-note` subcommand for IMPLEMENTER-NOTES (mirroring `append-non-goal`). `init` emits the notes and changelog paths; `approve`/`reject` delete the changelog along with the working copy.

**Why:** The always-reset behavior silently destroys unapproved fixes in every pause-and-resume flow — acute for a tool that brackets discussions with multiple runs. Failing loudly surfaces leftover state; plain `spec-improve` gets safer for free. All file operations stay in the script per repo convention. Breaking change, per this repo's stated preference over compatibility shims.

**Alternatives rejected:** Orchestrator discipline alone ("only call init once") — protects nothing across session crashes and resumes.

### D8: Deterministic floor = existing `citations` check + a new structure check; verification coverage stays LLM-judged

**Choice:** Per-round deterministic checks are `milestone_checks.py citations` (exists, standalone-capable) and a new `spec_checks.py structure <spec-path>` (asserts required template headings present, file non-empty). Scope↔verification coverage (#9) remains a lens-reviewer check.

**Why:** Deterministic checks cannot be sweet-talked and cost nothing — use them wherever no judgment is needed. But making #9 deterministic requires a citation-like link syntax between Scope bullets and Verification items — a template change rippling through spec-draft, spec-improve, and create-milestone. Wrong blast radius for this concept.

**Alternatives rejected:** Verification link syntax in the template (cross-command contract change; deliberately excluded); no floor at all (wastes gate budget on mechanically checkable failures).

### D9: Decision cards prepare the discussion; resolutions return as free-form directives

**Choice:** Each needs-user finding becomes a card: finding, codebase research, options with tradeoffs, recommendation, blast radius, dependency order — researched *after* the drain is dry. Cards are discussed in prose in the main conversation. Resolutions feed the next run as free-form prose directives that an apply agent executes before re-draining.

**Why:** The decisions that surface genuinely need back-and-forth (observed across spec-improve sessions); the card's job is to make that conversation well-armed, not shorter. Real discussions often end in "section 4's approach is wrong, redo it," not "option B" — a structured decision→answer map cannot carry that, prose directives can. Researching cards after the drain means research reflects the spec the decision will actually land in.

**Alternatives rejected:** AskUserQuestion pickers for resolution (flattens a discussion into a selection — recreates the original frustration); structured resolution schema (cannot express editorial redirections).

### D10: All cross-round state lives in files; agents stay context-free

**Choice:** Reviewers, judges, fixer, and researchers are spawned fresh every round with no memory. Cross-round knowledge exists only as files (NON-GOALS, IMPLEMENTER-NOTES, CHANGELOG, the working copy itself) plus the workflow script's loop variables (dry-round counter, card accumulator).

**Why:** Fresh eyes are the founding principle of `spec-improve` — a reviewer that remembers prior rounds starts filtering by memory instead of re-reading. Files-as-state also makes runs resumable and auditable, and matches how the rest of the repo persists pipeline state (JSON contracts, sidecars).

## Scope

### What gets built

- `spec/commands/spec-improve-auto.md` — command orchestrating the outer loop: guarded init, workflow invocations, card discussions, directive collection, final approval flow (D1, D2, D9)
- `spec/workflows/spec-improve-auto.js` — the drain-loop workflow script: lens fan-out, merge, gate panel, fixer, card researchers, termination logic; prompts inline; zero business logic (D2, D3, D4, D5)
- `spec/scripts/spec_checks.py` — new deterministic `structure` check, stdlib-only, importable, pytest-covered (D8)
- `improve_files.py` changes — init guard + `--fresh`, `append-note`, changelog/notes paths in init JSON, changelog deletion on approve/reject; updated tests (D7)
- `concept-IMPLEMENTER-NOTES.md` sidecar support — written via `append-note`, injected into gate prompts as prior-judgment memory (D6)
- Decision-card and directive contracts — the workflow return JSON and args JSON shapes as the stable interface between workflow runs and the conversation (D9)
- Per-fix changelog sidecar — one entry per applied fix (what/why/which finding), the audit trail replacing per-round human gates (D4, D10)
- `spec/install.sh` registration — COMMANDS entry, workflows/ copy step, `{MG_INSTALL_WORKFLOWS_DIR}` placeholder + sed pair; `spec-help.md` listing (D1, D2)

### What does NOT get built

- **Changes to `mg:spec-improve` behavior** — it remains the manual path; it inherits only the `improve_files.py` hardening (which makes it safer, not different).
- **Template changes** — no scope↔verification link syntax; the concept-spec template contract is untouched.
- **`spec-create-milestone` consumption of IMPLEMENTER-NOTES** — the sidecar is advisory for the human/implementer; projecting it into milestones is a separate concept if ever wanted.
- **Divergence detection for hand-edited originals** — if the user edits `concept.md` during a discussion pause, `approve` still clobbers it; the exposure exists in `spec-improve` today and is unchanged.
- **Token budget mechanism** — cost is accepted at this leverage point (a decision resolved pre-milestone is 5–10x cheaper than at implementation); the round cap is the only brake.

## Open Items

None — all decisions surfaced during drafting were resolved and promoted to D-blocks.

## Verification

- **init guard:** given an existing `concept-auto-improve.md`, `improve_files.py init` exits 1 without touching it; `init --fresh` resets it; init JSON contains `implementer_notes` and `changelog` keys. `approve`/`reject` remove the changelog. Covered by pytest.
- **append-note:** given a below-bar finding text, `append-note` creates/appends the IMPLEMENTER-NOTES file in NON-GOALS format; repeated appends preserve prior entries. Covered by pytest.
- **structure check:** given a spec missing a required template heading, `spec_checks.py structure` exits 1 naming the missing section; given the template-conformant fixture, exits 0. Covered by pytest.
- **Gate panel trial (subagent, during build):** given a synthetic finding list with a known substantive/cosmetic split, the 3-judge panel confirms the substantive ones and refutes the cosmetic ones with ≥2/3 agreement matching the expected partition.
- **Lens reviewer trial (subagent, during build):** given the real `gsd-mg-install/concept.md` (read-only), each lens reviewer returns findings only within its assigned dimensions.
- **Convergence dry-run:** given a fixture spec with planted issues (N mechanical, M decision-shaped), one workflow run fixes the mechanical ones with one changelog entry per fix, exits `blocked` with M cards carrying research/options/recommendation/blast-radius, and a follow-up run with directives applies them and exits `converged` within the round cap.
- **Gate memory:** given an IMPLEMENTER-NOTES file containing a previously judged below-bar finding, a subsequent round's gate does not re-confirm the same finding as substantive and does not append a duplicate note.
- **Determinism of the loop:** the same fixture and directives produce the same round count and status across runs (agent findings vary; control flow must not).
- **Install:** `install.sh --target <tmp>` places the command with all placeholders substituted (including `{MG_INSTALL_WORKFLOWS_DIR}`) and the workflow script under `.claude/spec/workflows/`.
- **Acceptance:** a full run on the next real concept spec converges without a manual abort, with every surfaced card being a genuine decision (user judgment).
