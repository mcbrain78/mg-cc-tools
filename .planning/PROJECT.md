# mg-cc-tools: /mg:docs Command Family

## What This Is

A documentation lifecycle tool for the mg-cc-tools collection that scans a project and generates/maintains audience-segmented documentation. It produces documentation for 4 audiences (end-users, developers, AI agents, devops) through a 3-step pipeline (scan, generate, verify), with a companion note-capture command for recording operational knowledge during development. First test target is the road-runner project.

## Core Value

Automate the creation and maintenance of audience-specific documentation so it stays current as code evolves, replacing the manual documentation process.

## Requirements

### Validated

<!-- Existing capabilities in the mg-cc-tools codebase -->

- ✓ Self-contained tool pattern with install.sh, commands/, agents/, scripts/, references/ — existing
- ✓ 3-step pipeline architecture (scan → process → verify) with shared JSON contract — existing (codebase-health)
- ✓ Parallel subagent spawning via Task tool — existing (codebase-health scanners)
- ✓ Python scripts for deterministic operations (may use established 3rd party packages) — existing
- ✓ Install-time path resolution via sed placeholders — existing
- ✓ Config layering (global defaults + project overrides) — existing (codebase-health)
- ✓ GSD integration (reading .planning/ state) — existing (update-backlog, debug-triage)
- ✓ Pipeline state detection and resume — existing (codebase-health)

### Active

<!-- New capabilities to build for /mg:docs -->

- [ ] 5 slash commands: create-docs (router), create-docs-scan, create-docs-generate, create-docs-verify, add-docs
- [ ] 4 audience subdirectories under docs/auto-doc/: end-users, developers, agents, devops
- [ ] 2 shared documents: OVERVIEW.md, GLOSSARY.md
- [ ] 11 audience-specific document types across 4 audiences
- [ ] 3-layer template architecture: classification (Diataxis) + structural (headings + purpose) + exemplar (examples)
- [ ] ~13 templates in references/templates/ organized by audience
- [ ] Scan step: project orientation, source material index, GSD context loading
- [ ] Staleness detection: code-reference checks, git-based freshness, schema drift, terminology drift
- [ ] Generate step: section-by-section generation with source material fed per section
- [ ] 5 writer agents (4 audience + glossary) running in parallel
- [ ] Update mode: staleness report → user approval → targeted section updates (not full rewrites)
- [ ] Verify step: reference integrity, cross-doc consistency, Diataxis mixing detection, completeness audit
- [ ] Notes inbox via /mg:add-docs with auto-classification (audience, document, section)
- [ ] Notes integration during generate step with expansion and placement
- [ ] Section ownership tracking via HTML comment markers (docs-meta)
- [ ] Schema definition for docs-scan.json shared data contract
- [ ] Style guide for cross-audience writing conventions
- [ ] 7 agent definitions: 4 audience writers, glossary writer, staleness scanner, verifier
- [ ] 5 Python scripts: add-note, classify-note, check-references, merge-scan, staleness-check
- [ ] install.sh with standard 3-mode support and project scaffolding (.mg/docs/)
- [ ] Project config (.mg/docs/.docs.config.json) for audience enable/disable and custom documents

### Out of Scope

- Auto-push documentation to external hosting (GitHub Pages, ReadTheDocs) — deployment is outside tool scope
- Image/diagram generation — LLMs can't produce images; ASCII diagrams only
- Non-Markdown output formats (PDF, HTML) — Markdown is the universal format
- Real-time documentation sync (file watchers, CI hooks) — run-on-demand via slash commands
- Multi-language documentation (i18n) — English only for v1

## Context

- The design document at `docs/work-queue/todo/doc-command/DESIGN.md` contains the complete v3 specification including research backing, format conventions per audience, template architecture, pipeline details, and data contract schema
- First test target is the road-runner project
- Follows the codebase-health pattern closely: 3-step pipeline, JSON data contract, parallel subagents, Python helpers, config layering
- Key differences from codebase-health: Step 2 is creative (writing docs), has approval gates, companion note-capture command, templates drive generation
- Research-backed decisions on format per audience (NNGroup, SmartBear, Diataxis, Google SRE, Codified Context paper)

## Constraints

- **Dependencies**: 3rd-party dependencies are fine when they bring real value — prefer well-maintained, known solutions. Do not reinvent the wheel. Declare them so the install process can manage them
- **Self-contained**: No cross-tool dependencies within mg-cc-tools — existing convention
- **Install modes**: Must support --project, --global, --target install modes — existing convention
- **Path resolution**: All resource references must use sed-replaceable placeholders — existing convention
- **Markdown output**: All generated documentation is Markdown (agent docs use YAML frontmatter for metadata)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Markdown for agent docs (not JSON/YAML) | 15-16% more token-efficient than JSON; industry standard (CLAUDE.md, AGENTS.md) | — Pending |
| Diataxis classification system | Widely adopted framework; prevents content type mixing | — Pending |
| Section-by-section generation | Research shows better quality than whole-document generation | — Pending |
| 3-layer templates (classification + structural + exemplar) | Research-backed sweet spot for LLM-generated doc quality | — Pending |
| Notes inbox as separate command | Captures operational knowledge during development without running full pipeline | — Pending |
| docs/auto-doc/ output directory | Separates generated docs from hand-written docs; clear ownership | — Pending |

---
*Last updated: 2026-03-15 after initialization*
