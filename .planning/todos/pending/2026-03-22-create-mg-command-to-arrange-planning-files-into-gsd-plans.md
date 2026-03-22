---
created: 2026-03-22T09:12:10.823Z
title: Create mg command to arrange planning files into GSD plans
area: tooling
files: []
---

## Problem

> **User input (verbatim):** write a mg command which takes a plan or directory with planning files and arranges them so that they fit well into individual gsd plans

When working with detailed phase plans (like the auto-doc-1.1 work-queue documents), the planning content needs to be decomposed into individual GSD-compatible plan files. Currently this is a manual process — the user writes phase docs, then separately creates GSD plans that reference or restate the same information. There's no tool to bridge the gap between freeform planning documents and GSD's structured plan format.

## Solution

Create an `/mg:plan-arranger` (or similar) command that:
1. Takes a plan file or directory of planning files as input
2. Analyzes the content to identify discrete, independently-executable work units
3. Generates GSD-compatible plan files (PLAN.md format) that map to the source material
4. Respects GSD plan constraints (atomic commits, clear task boundaries, verification criteria)

TBD: exact command name, whether it creates plans directly or proposes a structure for approval.
