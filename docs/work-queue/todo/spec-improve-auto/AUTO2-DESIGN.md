# `mg:spec-improve-auto` (auto2) — Lightweight-Loop Design & Implementation Spec

**Status: PROMOTED (2026-07-28).** auto2 won the promote-or-delete bet. The fork's content now *is* canonical `spec/` on namespace `/mg:`; `spec-temp/` and the Workflow drain (`spec/workflows/spec-improve-auto.js`) are deleted. The port carried over `spec-improve-auto.md`, `spec_checks.py`, `improve_files.py`, `agents/spec-reconcile.md`, `test_reconcile_audit.py`, and the `spec-help` blurb, and wired `agents/` + `{MG_INSTALL_RECONCILE_AGENT}` into `spec/install.sh`. Everything below describes that design — read `spec-temp/`/`mg-temp:` as `spec/`/`mg:`.

**Original framing (historical):** design → ready to implement. Isolated fork `spec-temp/` (namespace `/mg-temp:`), created + verified 2026-07-21. Existing `spec/` + `spec-improve-auto` are UNTOUCHED. Model = **promote-or-delete** (if auto2 wins → delete `spec/`, promote the fork; else delete the fork).

**This doc is the resume anchor for implementation after a context compaction.** It is self-contained: read it + the memory `project_spec_improve_auto_status` (PIVOT entry) and you can build without the prior conversation.

## UPDATE 2026-07-21 — round-1 validation reframed the build order (auto-decisions are CORE, not LATER)

Minimal loop built + committed (**b15d23a**); validated on a real 184-line spec (road-runner `split-safe-pit-l2`, from `concept.md.backup`). Run log: `scratchpad/auto2-val/RUN-LOG.md`.

**Round 1 result:**
- Loop mechanics work end-to-end (init → review → fix → floor → snapshot → exit-exam).
- **Exit-exam asymmetric bar VALIDATED** — the harsh reviewer found 10 findings (code-validated against road-runner); the substantive-only exit-exam filtered to the 2 that truly block an implementer and refused to false-CLEAN with the floor green. The anti-thrash termination signal is real; the "vacuous / false-converge" risk is **retired**.
- **But the surface-only loop cannot DRIVE or converge on a real spec.** It surfaced the decision points (the whole job of refinement) but had nowhere to put them → every `NEEDS_USER` finding parks → cap-stop dumping them on the user. **User's reframe: specs are NEVER decision-complete; surfacing decisions IS refinement; autonomy = driving THROUGH those decision points, not stopping at them.** So the original "validate termination first, add decisions later" order was backwards — you cannot reach autonomous termination without decision-driving, because the unresolved decisions are exactly what block convergence.

**Revised build order:**
- ~~LATER: auto-decisions~~ → **NOW: auto-decision-driving is the core of the loop.** Per round, each decision-shaped finding gets a scoped **research-and-decide** agent: read the *relevant* code/context (not the whole repo) → determine the defensible resolution + rationale + rejected alternatives → self-assess stakes. **Takeable** (clear best answer, bounded blast radius, doesn't reverse a stated non-goal/intent) → return the exact spec edit (write/repair the D-block, resolve the open item, correct the false premise); the orchestrator applies it + logs a decision-take. **Escalate** (genuinely ambiguous / high-stakes / wide radius / reverses intent) → framed choice for the human, NOT resolved. **Converged** = the exit-exam finds nothing substantive left *except* items explicitly escalated → present the briefing: every auto-take (for review/override) + the short human-required list.
- Aggressiveness default: auto-take everything defensible, escalate only high-stakes / intent-reversing, brief post-hoc (user's philosophy — [[feedback_swarm_design_philosophy]]).
- Caveat (unchanged from the fresh-eyes review): no ledger → blast-radius is agent-*judged*, not computed. Mitigation: decide-agent stays sharp (Opus); working-copy safety net (original untouched until approve); the briefing lists every take, so a bad call is visible + reversible, not silently locked in.

**Model tiering (per `EFFICIENCY-DESIGN.md`):** exit-exam + decide-agent = **Opus** (termination signal + sharp decisions; a wrong call in either is NOT self-correcting — a false-CLEAN ends the loop, a bad auto-take gets locked in). Reviewer = **Sonnet-5** (A/B spike passed 2026-07-21): on the same working copy + prompt, Sonnet caught BOTH crown-jewel code-contradictions (165-quarters, D4 placement) AND found new valid issues Opus missed (protocol-required `rejected` field, D6 cross-service impact, BACK-01 operational premise, citation errors) — quality holds/exceeds. Cheaper in $ (~5× lower per-token more than offsets ~2× token volume) but NOT faster (it read more; the run was also confounded by a platform outage). So model choice is a ~2× $ lever, not a speed win. **The bigger lever is a code-fact digest computed ONCE per run** (code is static across a run; only the spec changes) and handed to every agent — ~5–10×, stacks with tiering. This is the realization of "read once, branch": a **fork/shared-context primitive was checked for and is NOT available** on the Agent path (fresh subagents; `SendMessage` is sequential not parallel-independent; no cross-agent prefix cache — confirmed by the drain probe). So the digest (each agent reads a small facts file, not the repo; falls back to reading a specific file if the digest is thin) is the supported mechanism. **Build it WITH the decision-driving layer** — they share the agent-spawning path, and the digest is what makes the many decide-agents affordable to test.

**Cost finding:** each code-reading agent ≈ 110–127k subagent tokens, ~10–12 min. Agent COUNT is low (2–3/round vs the drain's 38 ✓) but each is a heavyweight code re-reader. Next efficiency lever after tiering: a code-fact digest computed once and cached across rounds (stop re-reading the same code every round).

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
