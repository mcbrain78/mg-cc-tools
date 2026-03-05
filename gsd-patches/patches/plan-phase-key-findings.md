# Patch: plan-phase-key-findings

## Meta
- **Target:** get-shit-done/workflows/plan-phase.md
- **Description:** Adds a Key Findings summary section to the plan-phase completion output, surfacing important decisions and discoveries so the user doesn't need to scroll through agent protocol messages

## Modifications

### 1. Add Key Findings section to offer_next template

Inserts a `### Key Findings` block between the verification status line and the Next Up separator. The orchestrator collects notable items from the planning session (checker warnings, research discoveries, decision tensions, executor notes) and presents them as a numbered list.

**Anchor:**
```
Research: {Completed | Used existing | Skipped}
Verification: {Passed | Passed with override | Skipped}

───────────────────────────────────────────────────────────────

## ▶ Next Up
```

**Replace with:**
```
Research: {Completed | Used existing | Skipped}
Verification: {Passed | Passed with override | Skipped}

### Key Findings

Summarize the most important discoveries and decisions from the planning session as a numbered list (typically 2-5 items). Include:
- **Checker warnings and resolutions** — what was flagged, how it was fixed, and the rationale
- **Research discoveries** — notable technical findings that shaped the plans (e.g., library limitations, infrastructure gaps, codebase patterns leveraged)
- **Locked-decision tensions** — cases where a technical recommendation conflicted with a user decision, and how it was resolved
- **Open questions for the executor** — info-level gaps the executor should be aware of during implementation

Omit categories that have no items. If the planning session was straightforward (no warnings, no tensions), a single bullet noting "No notable issues" is sufficient.

Each item should be 1-2 sentences — enough context to understand the decision without re-reading the full agent output.

───────────────────────────────────────────────────────────────

## ▶ Next Up
```
