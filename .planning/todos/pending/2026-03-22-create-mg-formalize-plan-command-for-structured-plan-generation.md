---
created: 2026-03-22T09:36:42.884Z
title: Create mg:formalize-plan command for structured plan generation
area: tooling
files: []
---

## Problem

> **User input (verbatim):** write mg:formalize-plan command which creates a plan out of the current context discussion and applies a best practice template / format

When working through planning discussions (like the auto-doc-1.1 work-queue documents or ad-hoc design conversations), the resulting decisions and scope are captured in freeform documents or conversation context. Converting these into properly structured GSD-compatible plans (PLAN.md files with tasks, verification criteria, dependencies) is a manual process that requires knowledge of GSD's plan format and best practices.

## Solution

Create an `/mg:formalize-plan` command that:
1. Takes the current discussion context (CONTEXT.md, conversation, or a source document) as input
2. Applies a best-practice plan template/format (GSD's PLAN.md structure)
3. Generates a properly structured plan with: task breakdown, file-level scope per task, verification criteria, dependency ordering, atomic commit boundaries
4. Ensures the output conforms to what GSD's executor expects

TBD: whether this wraps `/gsd:plan-phase` or is a standalone alternative for cases where the user has already done the thinking and just needs formatting.
