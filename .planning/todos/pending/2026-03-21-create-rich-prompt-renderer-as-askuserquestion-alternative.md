---
created: 2026-03-21T09:54:25.353Z
title: Create rich prompt renderer as AskUserQuestion alternative
area: tooling
files:
  - install.sh (multiple tools)
---

## Problem

The AskUserQuestion tool only supports a limited number of options and simple text prompts. The installer needs directory selection (e.g., choosing from multiple candidate directories) which requires more options and richer display than AskUserQuestion provides. There is no reusable "rich prompt" component in the toolset today.

## Solution

Generalize the existing Python renderer pattern into a reusable rich prompt system:

1. **Rendering .md** — a command/agent markdown file that the orchestrator calls. It defines the display layout and interaction contract.
2. **Python script** — builds the content (option lists, formatted output, etc.) and passes it to the rendering .md.
3. **Orchestrator flow** — orchestrator calls rendering .md, Python builds content, rendering .md displays it and captures the user's selection, returns result to orchestrator.

The existing Python renderer (likely in codebase-health or install tooling) can probably be generalized to serve as the foundation. Key requirements:
- Support arbitrary number of options (beyond AskUserQuestion's limit)
- Support directory selection use case for installer
- Reusable across tools (not tool-specific)
