---
created: 2026-03-17T16:06:14.742Z
title: Fix shell metacharacter escaping in add-finding CLI args
area: codebase-health
files:
  - codebase-health/scripts/add-finding.py
  - codebase-health/scripts/verify-finding.py
  - codebase-health/agents/TEMPLATE.md
---

## Problem

The `add-finding.py` and `verify-finding.py` scripts accept free-text fields (`--evidence`, `--notes`, `--reasoning`, `--proposed-change`) as CLI arguments. When an LLM agent constructs a bash command containing text with shell metacharacters (backticks, dollar signs, quotes, parentheses), bash interprets them before the script receives them.

Example: a finding with description `Schema name `etl_runs` should be `road_runner`` becomes command substitution when passed as `--evidence "Schema name `etl_runs` should be `road_runner`"`. Double quotes don't protect against backtick expansion. Single quotes break if the text contains single quotes.

This hasn't caused visible failures yet because the evidence text in codebase-health scans tends to be simpler, but it's a latent bug that will surface with richer content.

## Solution

Switch free-text input from CLI arguments to a temp-file-based pattern: agent writes finding data to a temp JSON file via the Write tool, then calls the script with `--input /path/to/temp.json`. The script reads, validates, and appends to the consolidated findings file. No shell escaping anywhere in the chain.

This is the same fix being designed for the new create-docs verify pipeline scripts. Both pipelines should use the same input pattern.
