---
created: 2026-03-30T09:45:03.725Z
title: Simplify auto-doc writer agents and move ref emission to writer
area: auto-doc
files:
  - auto-doc/agents/devops-writer.md
  - auto-doc/agents/end-user-writer.md
  - auto-doc/agents/developer-writer.md
  - auto-doc/agents/agent-writer.md
  - auto-doc/scripts/write-section.py
  - auto-doc/scripts/extract-refs.py
  - auto-doc/agents/ref-extractor.md
  - auto-doc/agents/section-verifier.md
---

## Problem

The writer agents have accumulated technical debt from iteration. Key issues:

1. **Haiku verification in writer is redundant.** Step 3f/3h calls verify-section-refs.py (Haiku) per section during generation. With the new XML pipeline, verify-xml-refs.py and verify-prose.md handle this post-generation more reliably. The in-writer check adds ~30s latency per section and 18 lines of instructions.

2. **Ref extraction is in the wrong place.** extract-refs.py (Haiku) tries to reconstruct structured refs from prose after the fact. The writer (Opus) had full source context when writing but discarded it. Haiku then guesses from paraphrased text — e.g., "the ETL run log" → can't infer schema `road_runner`, table `etl_runs`. First generate run showed key-concepts getting 0 refs and glossary getting spurious refs like `_impl_flow_name` (a pattern description, not a function).

3. **Writer instructions are verbose.** Template comment handling (SYNTHESIZED/BOUNDARY/OPTIONAL) takes 32 lines but could be 3. Interface style determination is 9 lines but could be 2. Template change migration note is stale. `calls` field explanation is dead weight for non-developer audiences.

## Solution

**Move typed ref emission to the writer.** The writer already emits `{"symbols": [], "file_paths": []}`. Extend to `{"symbols": [], "file_paths": [], "typed_refs": [...]}` using the 6-type schema (db/code/flow/env/config/enum). Writer has full context to emit precise refs.

**Flip Haiku from extractor to auditor.** extract-refs.py becomes audit-refs.py — reads prose + writer's refs, flags gaps ("prose mentions X but no ref for it"). Much easier task for a small model (comparison vs inference).

**Remove in-writer Haiku verification (step 3f/3h).** Advisory symbol validation in write-section.py (`--project-root`) catches the same class of errors. Post-generation verify pipeline catches the rest.

**Compress instructions.** Target ~140 lines from ~199 (end-user writer baseline). Remove stale migration notes, compress template comment handling, simplify interface style logic.

**Iterate on devops first.** Devops has highest ref density (db/flow/env/config/enum) with lowest writer complexity. Best test case for the XML ref pipeline. Then transfer to developers, agents, end-users.
