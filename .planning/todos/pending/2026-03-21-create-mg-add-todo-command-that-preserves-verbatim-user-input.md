---
created: 2026-03-21T09:57:41.879Z
title: Create mg:add-todo command that preserves verbatim user input
area: tooling
files:
  - commands/ (new command)
---

## User Input

> make mg:add-todo command which always adds "CRITICAL INSTRUCTION: PRESERVE USER INPUT IN VERBATIM as USER INPUT SECTION" since that information gets lost. ADD THIS USER INPUT EXACTLY AS STATED in addition to your analysis

## Problem

When using `/gsd:add-todo`, the LLM rewrites and interprets the user's input into structured Problem/Solution sections. The original user wording — which may contain nuance, specific phrasing, or intent that the LLM misses — is lost. There is no verbatim record of what the user actually said.

## Solution

Create an `/mg:add-todo` command (wrapping or extending `/gsd:add-todo` behavior) that includes a critical instruction to always preserve the user's raw input verbatim in a dedicated "User Input" section, in addition to the LLM's analysis in Problem/Solution sections. The command .md file should contain an instruction like:

```
CRITICAL INSTRUCTION: PRESERVE USER INPUT VERBATIM as a "## User Input" section.
Add the user's exact words as a blockquote, in addition to your Problem/Solution analysis.
```

This ensures the original intent and phrasing survives for future context, while still getting the structured analysis.
