# `mg-temp:spec-improve-auto` (auto2) — Lightweight-Loop Design & Implementation Spec

**Status:** design → ready to implement. Isolated fork `spec-temp/` (namespace `/mg-temp:`), created + verified 2026-07-21. Existing `spec/` + `spec-improve-auto` are UNTOUCHED. Model = **promote-or-delete** (if auto2 wins → delete `spec/`, promote the fork; else delete the fork).

**This doc is the resume anchor for implementation after a context compaction.** It is self-contained: read it + the memory `project_spec_improve_auto_status` (PIVOT entry) and you can build without the prior conversation.

## Why (the pivot)
The Workflow drain (`spec/workflows/spec-improve-auto.js`, 1378 lines) is **~10× too expensive**: measured 16.5M tokens / 2 rounds / 77 agents on a 62-line fixture, never converged (`EFFICIENCY-DESIGN.md`). Root cause: cost scales with **agent COUNT** — a caching probe (`wf_7640160e-133`) proved the runtime does NOT cross-agent-cache doc context, so a swarm can't amortize it. A fresh-eyes architect review (`scratchpad/auto2-decision-brief.md`) returned **DIFFERENT design (med-high confidence): keep the drain's phase-H macro loop, DROP the per-atom verification pyramid.** Phase H = spec-improve's reviewer and produced ALL observed value; the pyramid is the expensive, unproven part (its verify sweep never even completed in the run).

## Architecture — a main-session auto-loop (NOT the Workflow tool)
The command `.md` orchestrates the loop directly in the main session (like `spec-improve`), but autonomously (no per-round human gate). Per round:

1. **Macro review** — spawn 1–3 FRESH reviewer subagents (Agent tool), each a holistic whole-doc review over the working copy + concept template + any cited code (reuse the `spec-improve` reviewer prompt, incl. its decision-quality / citation-discipline checks). Each returns findings {severity, location, what's wrong, suggested fix, decision_shaped?}.
2. **Triage + fix** — orchestrator dedups findings against on-disk `IMPLEMENTER-NOTES` / decisions, then Edit-applies the fixes it's confident in to the **working copy**; logs each via `improve_files.py append-changelog`. Cap per round (~10) to bound blast radius.
3. **Deterministic floor** — `spec_checks.py floor <working-copy>` (structure + citations) must pass; floor findings re-enter triage.
4. **Snapshot** — `improve_files.py snapshot` → `history/run-N/round-M.md` (audit trail; NOT held in context).
5. **Termination check** — spawn ONE FRESH "exit-exam" reviewer (whole-doc, different lens: "is anything *substantive* still wrong or missing?"). **Converged** iff exit-exam returns no actionable findings AND floor passes. Else carry findings → next round.
6. **Round cap** safety backstop (e.g. 20).

On convergence: summarize the run (changelog + briefing) → user approves (`improve_files.py approve`; working-copy safety net unchanged — original untouched until approve).

**State discipline (LOAD-BEARING — the #1 failure mode):** the orchestrator keeps NOTHING durable in its own context. Every round it re-reads the working copy + sidecars from disk (`improve_files.py paths`) and spawns FRESH stateless reviewers. This is what lets one main session survive 10–20 rounds without context blowup. There is NO orchestrator "continuity" edge (that was a wrong earlier claim); the real edge is **cost + simplicity + resumability**.

## Reuse (COPIED into the fork; invoked path-based via `uv run`, never imported)
- `improve_files.py` — init / paths / snapshot / append-changelog / append-note / approve / reject.
- `spec_checks.py` — `structure`, `citations`, `floor` now; `briefing` / `decisions` / `tally` later.
- DROP for the minimal loop: the `atoms` ledger + verification pyramid, the drain `.js`, all Workflow orchestration.

## Build order
**NOW — minimal loop (the termination-test vehicle):** rewrite `spec-temp/commands/spec-improve-auto.md` as the main-session loop above. `allowed-tools`: Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion — **NO Workflow**. Reviewer → triage/fix → floor → snapshot → exit-exam → loop. **NO auto-decisions, NO tiering yet.** Delete `spec-temp/workflows/` and the drain-specific parts of the command. Update `spec-temp/install.sh` if the workflows copy step is now unused (drop it). Update `spec-temp/commands/spec-help.md` blurb.

**THEN — validate the load-bearing bet:** run the minimal loop on a REAL ~200-line spec (not the 62-line toy). Log per round: finding count, new-vs-repeat, and **does the exit-exam ever return clean, at what round?**
- Terminates at 10–20 rounds → design holds; build out.
- Thrashes (exit-exam never clean) → need more determinism; learned cheaply, before investing further.

**LATER (only after termination holds):**
- **Auto-decisions** — research subagent + take; small auto-taken, wide-radius surfaced; briefing for review. CAVEAT (review): without the ledger, `block-gate`'s radius runs on the researcher's estimate alone → decisions become more LLM-judged, and a wrong auto-take is locked in unless a re-open path is added. Keep decisions the SHARP (full-accuracy) role.
- **Model tiering + batching** — per `EFFICIENCY-DESIGN.md`: cheapen self-correcting/mechanical roles (readers/relays), keep decisions sharp; Haiku needs a Gate-B-style transcription-fidelity spike first.

## Caveats from the fresh-eyes review (do not forget)
1. **Termination is JUDGED, not deterministic.** `floor` passes early on a template-conformant spec (near-vacuous as a stop signal). Real termination = the exit-exam going dry — the relative-grader problem. Build + validate it AS a judged exit-exam; don't call it deterministic.
2. **Decision safety regresses without the ledger** — address when decisions are built.
3. **Context-growth is the top risk** — stateless-per-round + disk state, always.
4. Evidence leans FOR the pivot (run round-2: 0 re-emergence + genuinely-new issues = backlog-drain, not thrash; user reports spec-improve *converges* in 10–20 rounds) — but auto (no-human) termination at realistic round counts is unproven. That's the validation's job.

## Pointers
- Fresh-eyes review brief: `scratchpad/auto2-decision-brief.md`
- Efficiency baseline + lever catalog + tiering + A/B plan: `EFFICIENCY-DESIGN.md`
- Original drain concept (its D2 `drain_state.py` + D3 no-ledger hybrid are the named fallbacks this realizes): `concept.md`
- Resume anchor: memory `project_spec_improve_auto_status` (PIVOT 2026-07-21 entry)
- Fork lives at `spec-temp/` (namespace `/mg-temp:`); `spec/` is untouched; both install side-by-side (verified).
