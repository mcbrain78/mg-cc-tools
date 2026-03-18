# Patch: execute-phase-key-findings

## Meta
- **Target:** get-shit-done/workflows/execute-phase.md
- **Description:** Adds a Key Findings summary to the execute-phase completion output. Surfaces wave descriptions, deviations, decisions, patterns, next-phase readiness, and user setup from SUMMARY.md files so the user doesn't need to read them separately.

## Modifications

### 1. Add present_findings step before offer_next

Inserts a `<step name="present_findings">` between `update_roadmap` and `offer_next`. The orchestrator recalls wave descriptions from its own earlier output and reads SUMMARY.md files to extract deviations, decisions, patterns, readiness, and setup requirements. These are presented as a consolidated summary that the user sees before routing (auto-advance or manual).

**Anchor:**
```
<step name="offer_next">

**Exception:** If `gaps_found`, the `verify_phase_goal` step already presents the gap-closure path (`/gsd:plan-phase {X} --gaps`). No additional routing needed — skip auto-advance.
```

**Replace with:**
```
<step name="present_findings">
**Present the final phase execution summary with Key Findings.**

Skip this step if `gaps_found` (the gap-closure output from `verify_phase_goal` is sufficient).

After `update_roadmap` completes and before any routing, present the phase completion summary. This is the user's primary record of what happened during execution.

Output this markdown directly (not as a code block):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GSD ► PHASE {X} COMPLETE ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Phase {X}: {Name}** — {M}/{total} plans | Verification: {Passed (N/N) | Gaps Found}

| Wave | Plans | Status |
|------|-------|--------|
| 1    | {plans} | ✓ Complete |
| 2    | {plans} | ✓ Complete |

### What Was Built

For each wave, include the rich plan description you displayed in the wave banner during execution — the full paragraph under the plan title that explains what the wave builds and why, NOT just a one-liner.

### Key Findings

Read all `*-SUMMARY.md` files in the phase directory. Extract and present these sections as a consolidated summary across all plans:

1. **Deviations from Plan** — List each deviation with its category (bug, blocking, etc.), what was found, and how it was fixed. These are in the `## Deviations from Plan` section of each SUMMARY.md.
2. **Decisions Made** — Implementation choices the executor made, especially those affecting architecture or future phases. Found in `## Decisions Made` or `key-decisions` frontmatter.
3. **Patterns Established** — New conventions created during execution that future phases should follow. Found in `patterns-established` frontmatter.
4. **Next Phase Readiness** — What's ready for downstream work, any blockers or concerns. Found in `## Next Phase Readiness` of the last plan's SUMMARY.md.
5. **User Setup Required** — Any manual steps the user needs to take (API keys, DB migrations, config). Found in `## User Setup Required`. Only include if any plan has a non-"None" value.

Omit categories that have no items across all plans. If everything went cleanly (no deviations, no notable decisions, no new patterns), a single line stating "No deviations or notable decisions" is sufficient.

Each item should be 1-2 sentences — enough context to understand the finding without reading the full SUMMARY.md.

───────────────────────────────────────────────────────────────

## ▶ Next Up

**Phase {next}: {next_name}** — {one-line description}

`/gsd:plan-phase {next}`

<sub>`/clear` first → fresh context window</sub>

───────────────────────────────────────────────────────────────

**Also available:**
- `/gsd:progress` — check overall milestone progress
- `/gsd:verify-work {X}` — manual UAT testing

───────────────────────────────────────────────────────────────
</step>

<step name="offer_next">

**Exception:** If `gaps_found`, the `verify_phase_goal` step already presents the gap-closure path (`/gsd:plan-phase {X} --gaps`). No additional routing needed — skip auto-advance.
```
