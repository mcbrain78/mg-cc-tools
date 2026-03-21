---
created: 2026-03-21T22:42:38.957Z
title: Add auto-loop mode to auto-improve command
area: tooling
files:
  - docs/work-queue/todo/auto-improve-command-v1/auto-improve-plan.md
---

## User Input (verbatim)

> make auto-improve command auto loop until it thinks it should stop and only pause if user decisions are needed. these user decisions should be presented with askusertool. RECORD THIS TEXT AS USER INPUT IN VERBATIM in addition to your analysis

## Problem

The auto-improve command currently requires the user to manually invoke each round (`execute @auto-improve-plan.md @target-file.md`). After each round, the user must read the report, approve/reject, and then re-invoke for the next round. This creates friction — the user has to babysit what should be an autonomous improvement loop.

The workflow should automatically loop (review → triage → fix → validate → report) until it determines no more actionable issues remain, only pausing when user decisions are needed (approve/reject fixes, approve/reject non-goals).

## Solution

Modify the auto-improve plan to add an auto-loop mode:

1. After Step 7 (Report), use `AskUserQuestion` to present approval decisions instead of printing a report and stopping
2. After the user approves fixes/non-goals, automatically check if remaining solvable issues > 0
3. If yes, loop back to Step 1 (launch fresh reviewer) without requiring the user to re-invoke the command
4. If no (remaining solvable = 0, or all issues are cosmetic/skipped), stop and report "auto-improve complete"
5. Add `AskUserQuestion` to the workflow's implicit tool requirements

Key design questions to resolve:
- Should there be a max-rounds cap (e.g., 5 rounds) to prevent infinite loops?
- Should the loop stop when only minor/cosmetic issues remain, or only when zero issues are flagged?
- How to handle the case where the same issue keeps appearing across rounds (reviewer keeps flagging, fixer keeps not fixing)?
