---
created: 2026-03-22T11:36:28.712Z
title: Add pyright strict mode compliance
area: tooling
files:
  - codebase-health/scripts/*.py
  - auto-doc/scripts/*.py
---

## Problem

The Python scripts in mg-cc-tools (codebase-health and auto-doc pipelines) will be deployed into target projects that may enforce pyright strict mode. Currently the scripts lack type annotations and may use patterns that fail strict type checking, causing errors or warnings in those environments.

## Solution

- Add type annotations to all Python scripts across tools
- Fix any pyright strict mode violations (implicit Any, missing return types, untyped function parameters)
- Consider adding a pyright config and CI check to prevent regressions
