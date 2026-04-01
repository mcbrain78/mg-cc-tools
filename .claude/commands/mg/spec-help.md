# Spec Help

---
name: mg:spec-help
description: Show the spec command pipeline and usage guide
allowed-tools: []
---

```
The spec commands turn ideas into GSD-ready phases. They take you from a rough
idea or conversation through a formalized concept doc, then break that concept
into phases in ROADMAP.md with locked decisions in CONTEXT.md files. Each step
is optional — enter the pipeline wherever your work already is.

Spec Pipeline
=============

  spec-draft ──→ spec-improve ──→ spec-gsd-phases ──→ spec-prepare-context ──→ spec-create-context
   (idea)          (refine)        (add phases)         (split by phase)        (lock decisions)

Entry points
------------

  Start from an idea or conversation:
    /mg:spec-draft

  Start from an existing concept doc:
    /mg:spec-gsd-phases docs/work-queue/todo/{name}/concept.md

  Phases already exist, concept needs splitting:
    /mg:spec-prepare-context 1-5 docs/work-queue/todo/{name}/concept.md

  Single phase, source file ready:
    /mg:spec-create-context 3 docs/work-queue/todo/{name}/phase-docs/phase-03-foo.md

Commands
--------

  /mg:spec-draft [<file>]                     Turn a discussion and existing context into a concept spec.
                                              Asks questions on gray areas, contradictions, gaps.
  /mg:spec-improve <file>                     Review and refine an existing concept spec.
                                              Uses fresh-eyes subagents to surface blind spots.
  /mg:spec-gsd-phases <file>                  Analyze concept, propose and create GSD phases
  /mg:spec-prepare-context <range> <file>     Split concept into per-phase files
  /mg:spec-create-context <phase> <file>      Convert per-phase file to GSD CONTEXT.md

After spec
----------

  /mg:discuss-milestone          Cross-cutting + per-phase discussion
  /mg:plan-phase <N>             Derive requirements, then plan
  /mg:execute-phase <N>          Execute with deviation tracking
```
