---
created: 2026-04-30T08:24:57.255Z
title: Integrate entity extraction and dangling-prose check into auto-doc generator
area: auto-doc
files:
  - auto-doc/commands/auto-doc-generate.md
  - auto-doc/agents/developer-writer.md
  - auto-doc/agents/end-user-writer.md
  - auto-doc/agents/devops-writer.md
  - auto-doc/agents/agent-writer.md
  - auto-doc/agents/glossary-writer.md
---

## Problem

User request (verbatim):

> improce auto-doc-generate process by integrating entity extraction & "dangling prose check" into the generator. after each segment written, return to the orchestrator which calls an extractor and verfier subagent, if there are any issues, use send message to restart the old writer agent with an issue list. otherwise restart the old writer agent with the next segment it should write. End of april 2026 restarting agents once they have completed does not work yet and send message is an experimental feature. hence this re-write is postponed to a later release of auto-doc. RECORD THIS MESSAGE IN VERBATIM

## Solution

Postponed. Blocked by Claude Code platform limitations as of end of April 2026:

- Restarting/resuming a subagent after it has completed is not yet reliably supported.
- `SendMessage` is gated behind `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and explicitly experimental, with documented gaps (e.g., `/resume` does not restore in-process teammates).

Revisit once SendMessage moves out of experimental status and cross-turn agent resumption is stable. At that point, redesign `auto-doc-generate` so:

1. Writer subagent emits one segment, then yields to the orchestrator.
2. Orchestrator calls extractor + verifier subagents on the just-written segment.
3. If issues found → `SendMessage` to the original writer with the issue list to revise.
4. If clean → `SendMessage` to the original writer with the next segment to write.
5. Loop until all segments complete.

The benefit is incremental verification (catch dangling prose / missing refs per segment) without losing the writer's accumulated context across turns.
