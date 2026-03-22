---
created: 2026-03-22T09:19:54.090Z
title: Create mg:add-phase-with-context compound command
area: tooling
files: []
---

## Problem

> **User input (verbatim):** write a mg:add-phase-with-context command which first calls gsd:add-phase and then mg:create-context

When adding phases that have existing planning documents (like the auto-doc-1.1 work-queue files), the user currently needs to run two separate commands sequentially: `/gsd:add-phase <description>` to create the phase in the roadmap, then `/mg:create-context <phase-number> <source-file>` to import the planning document as locked decisions. This is tedious when adding multiple phases with associated docs.

## Solution

Create an `/mg:add-phase-with-context` compound command that:
1. Takes a phase description and source file path as arguments
2. Calls `/gsd:add-phase` (or its underlying `gsd-tools.cjs phase add`) to create the phase entry
3. Extracts the new phase number from the result
4. Calls the `/mg:create-context` logic to import the source document into the new phase's CONTEXT.md
5. Returns the combined result (phase created + context imported)

TBD: exact argument format (e.g., `<description> --source <path>` or positional).
