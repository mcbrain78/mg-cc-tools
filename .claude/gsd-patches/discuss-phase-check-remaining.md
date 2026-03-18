# Patch: discuss-phase-check-remaining

## Meta
- **Target:** get-shit-done/workflows/discuss-phase.md
- **Description:** Adds `--check-remaining` flag to discuss-phase for targeted gray area discovery on phases with existing context

## Modifications

### 1. Add `--check-remaining` flag handling to check_existing

Adds a `--check-remaining` flag that skips the update/view/skip prompt and jumps straight to analyzing remaining gray areas. Also adds a "Check for remaining areas" interactive option.

**Anchor:**
```
**If exists:**
Use AskUserQuestion:
- header: "Context"
- question: "Phase [X] already has context. What do you want to do?"
- options:
  - "Update it" — Review and revise existing context
  - "View it" — Show me what's there
  - "Skip" — Use existing context as-is

If "Update": Load existing, continue to analyze_phase
If "View": Display CONTEXT.md, then offer update/skip
If "Skip": Exit workflow
```

**Replace with:**
```
**If exists:**

First, check if `--check-remaining` flag was passed in $ARGUMENTS. Parse the quoted instruction text after the flag (e.g., `--check-remaining "Milestone-level decisions are already captured..."`).

**If `--check-remaining` is present:**
Log: "Checking for remaining gray areas..."
Load existing CONTEXT.md. Continue to analyze_phase with the flag's instruction text as the `remaining_instruction` — this text will be used in analyze_phase to guide which gray areas to focus on.

**If `--check-remaining` is NOT present:**
Use AskUserQuestion:
- header: "Context"
- question: "Phase [X] already has context. What do you want to do?"
- options:
  - "Update it" — Review and revise existing context
  - "View it" — Show me what's there
  - "Check for remaining areas" — Discuss any gray areas not yet covered by existing decisions
  - "Skip" — Use existing context as-is

If "Update": Load existing, continue to analyze_phase
If "View": Display CONTEXT.md, then offer update/skip/check-remaining
If "Check for remaining areas": Load existing, continue to analyze_phase with `remaining_instruction`: "Existing context provides a foundation. Focus on uncovered gray areas — aspects not yet addressed by current decisions."
If "Skip": Exit workflow
```

### 2. Use `remaining_instruction` in analyze_phase

When `remaining_instruction` is set (from `--check-remaining` or interactive "Check for remaining areas"), filter gray area generation to only uncovered aspects.

**Anchor:**
```
<step name="analyze_phase">
Analyze the phase to identify gray areas worth discussing. **Use both `prior_decisions` and `codebase_context` to ground the analysis.**
```

**Replace with:**
```
<step name="analyze_phase">
Analyze the phase to identify gray areas worth discussing. **Use both `prior_decisions` and `codebase_context` to ground the analysis.**

**If `remaining_instruction` is set** (from `--check-remaining` flag or "Check for remaining areas" option):
Apply this instruction when generating gray areas: {remaining_instruction}
Read the existing CONTEXT.md `<decisions>` section and treat all existing decisions as already settled. Only generate gray areas for aspects NOT covered by existing decisions.
```
