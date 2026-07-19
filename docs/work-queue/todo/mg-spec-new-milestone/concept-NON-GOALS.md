# mg:spec-create-milestone — Non-Goals

Explicit scope exclusions that must persist across review rounds. If a review round proposes any of these, it is re-opening a settled boundary.

- **NG1 — No GSD patches.** The command produces only files GSD already understands (`REQUIREMENTS.md`, roadmapper-written `ROADMAP.md`/`STATE.md`, `PROJECT.md`). It never modifies GSD workflows/agents/templates. (D6; mirrors `mg:spec-create-context`.)
- **NG2 — Does not replace `gsd:new-milestone`.** That command remains the correct path for greenfield / no-frozen-spec milestones (top-down discovery + elicitation). This is the spec-first sibling, not a substitute.
- **NG3 — Does not author or edit the spec.** The frozen concept is an input, produced upstream by `mg:spec-draft` → `mg:spec-improve`. The command reads it; it never writes back to `concept.md`.
- **NG4 — No new researcher agent.** The verification pass reuses `gsd-project-researcher` (steered by a spec-seeded verification prompt + single-file `<output>` redirect — see Stage 2), not a purpose-built agent. (D2.)
- **NG5 — No blind domain discovery, no per-category elicitation.** These are the two `new-milestone` behaviors deliberately removed; research is re-aimed to spec-verification only, and requirements are projected, not elicited. (D1/D2.)
- **NG6 — No un-vetted beyond-spec scope.** Nothing outside the spec enters the requirements except a Stage-2 research-flagged, operator-approved addition. No freeform `--also` scope input. (D3.)
- **NG7 — No phase-CONTEXT auto-seeding.** Seeding each phase's `CONTEXT.md` from the spec is owned by the existing downstream commands (`mg:spec-prepare-context` → `mg:spec-create-context`); this command stops at `ROADMAP.md` and hands off with the exact next commands (Stage 6). Division of labor with shipped tools, not a deferral.
- **NG8 — No gating of downstream `plan-phase` 5d additions.** `mg:plan-phase` step 5d may append requirements without operator approval after the Stage-6 handoff; changing that command's behavior is out of scope for this one. The mitigation is the Stage-6 handoff caveat plus a `milestone_checks.py check` re-run, which flags the row-less checkboxes. Reviewers should not flag 5d's gate bypass as a hole in this command.
- **NG9 — Contract density is intentional, not a defect.** The spec pins interface contracts (decision tables, the citation grammar, invariants, per-subcommand behavior) verbatim to prevent two-implementer drift — a value the spec itself states. Reviewers should flag genuine ambiguity or incorrectness, not prose length/verbosity per se.
