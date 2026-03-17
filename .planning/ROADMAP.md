# Roadmap: /mg:docs Documentation Lifecycle Tool

## Overview

Build a documentation lifecycle tool that scans a project and generates audience-segmented documentation through a 3-step pipeline (scan, generate, verify). The work progresses from foundational infrastructure (scripts, schema, config) through static content authoring (templates, agent definitions), then sequentially through each pipeline step (scan, generate, verify), culminating in the integration commands that tie everything together. First test target is road-runner.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation & Infrastructure** - Python scripts, schema, config, install.sh, style guide, project scaffolding
- [x] **Phase 2: Templates & Agent Definitions** - Three-layer template architecture, ~13 templates, 7 agent definitions, parallel execution setup
- [x] **Phase 3: Scan Pipeline** - Project orientation, source material index, staleness detection, notes classification, gap analysis, scan command
- [x] **Phase 4: Generate Pipeline** - Section-by-section generation, update mode, notes integration, all 13 document types, generate command
- [x] **Phase 5: Verify, Notes Command & Router** - Reference integrity, cross-doc consistency, Diataxis checks, completeness, add-docs command, router command
- [ ] **Phase 6: Fix Verify Feedback Loop & Scan Output** - Close verify-generate feedback loop, validate scan agent JSON output, file-based I/O pattern

## Phase Details

### Phase 1: Foundation & Infrastructure
**Goal**: All supporting infrastructure exists so pipeline steps and commands can be built on top of them
**Depends on**: Nothing (first phase)
**Requirements**: INF-01, INF-02, INF-03, INF-04, INF-05, INF-06, INF-07, INF-08, INF-09, INF-10
**Success Criteria** (what must be TRUE):
  1. Running `install.sh --project` on a test directory creates `.claude/commands/mg/`, `.claude/create-docs/agents/`, `.claude/create-docs/scripts/`, `.claude/create-docs/references/` with correct structure and sed-resolved paths
  2. Running `install.sh --project` scaffolds `.mg/docs/` with default config, empty notes inbox, and scan-logs directory
  3. Each Python script (add-note, classify-note, check-references, merge-scan, staleness-check) can be invoked standalone and produces correct JSON output for valid input
  4. `references/schema.md` defines the complete `docs-scan.json` data contract with all fields documented
  5. `references/style-guide.md` contains cross-audience writing conventions that writer agents can follow
**Plans:** 4 plans

Plans:
- [x] 01-01-PLAN.md — Foundation files: shared lib, schema, style guide, config, command stubs
- [x] 01-02-PLAN.md — Python scripts: add-note, classify-note, merge-scan with tests
- [x] 01-03-PLAN.md — Python scripts: check-references, staleness-check with tests
- [x] 01-04-PLAN.md — install.sh with three-mode support, sed resolution, project scaffolding

### Phase 2: Templates & Agent Definitions
**Goal**: All static content files (templates and agent prompts) are authored so the pipeline can use them for generation
**Depends on**: Phase 1
**Requirements**: TPL-01, TPL-02, TPL-03, AGT-01, AGT-02, AGT-03, AGT-04, AGT-05, AGT-06, AGT-07, AGT-08
**Success Criteria** (what must be TRUE):
  1. Each of the ~13 templates in `references/templates/` contains all three layers: Diataxis classification comment, structural headings with purpose statements, and concrete exemplar per section
  2. Optional sections are explicitly marked with `<!-- OPTIONAL -->` comments in every template where applicable
  3. Each of the 4 audience writer agents (end-user, developer, agent, devops) contains audience-specific format conventions, Diataxis guidance, and instructions for section-by-section generation
  4. Glossary writer, staleness scanner, and verifier agent definitions contain complete operational instructions for their specialized roles
  5. Agent definitions include instructions for parallel execution (one writer per audience + glossary concurrently)
**Plans:** 4/4 plans executed

Plans:
- [x] 02-01-PLAN.md — Shared agent pattern (TEMPLATE.md), glossary writer, shared + end-user templates
- [x] 02-02-PLAN.md — Developer, agent, and devops audience templates (9 templates)
- [x] 02-03-PLAN.md — Four audience-specific writer agent definitions
- [x] 02-04-PLAN.md — Staleness scanner, verifier agents, and install.sh templates patch

### Phase 3: Scan Pipeline
**Goal**: The scan step analyzes a project and produces a complete docs-scan.json that downstream generation can consume
**Depends on**: Phase 2
**Requirements**: SCN-01, SCN-02, SCN-03, SCN-04, SCN-05, SCN-06, SCN-07, SCN-08, CMD-02
**Success Criteria** (what must be TRUE):
  1. Running `/mg:create-docs-scan` on a project produces a valid `docs-scan.json` containing project model (tech stack, components, entry points), source material index (code files mapped to document sections), and gap analysis
  2. On a project with existing docs, the scan detects stale sections via code-reference checks (dead file paths, missing symbols) and git-based freshness (source files changed since section generated)
  3. On a project with `.planning/` directory, the scan loads GSD context (phase summaries, requirements traceability, verification gaps) into the scan output
  4. Pending notes in `notes-inbox.json` are classified with audience, document, section, and confidence level in the scan output
**Plans:** 2 plans

Plans:
- [x] 03-01-PLAN.md — Scan-audience subagent template and full create-docs-scan.md command
- [x] 03-02-PLAN.md — Install validation, test suite verification, and user smoke test

### Phase 4: Generate Pipeline
**Goal**: The generate step creates or updates all audience-segmented documents section-by-section using templates and scan results
**Depends on**: Phase 3
**Requirements**: GEN-01, GEN-02, GEN-03, GEN-04, GEN-05, GEN-06, DOC-01, DOC-02, DOC-03, DOC-04, DOC-05, DOC-06, DOC-07, DOC-08, DOC-09, DOC-10, DOC-11, DOC-12, DOC-13, CMD-03
**Success Criteria** (what must be TRUE):
  1. Running `/mg:create-docs-generate` in initial mode on a scanned project creates all 13 document types across `docs/auto-doc/` with shared OVERVIEW.md and GLOSSARY.md at root plus audience subdirectories (end-users, developers, agents, devops)
  2. Each generated section contains a `docs-meta` HTML comment tracking last-updated timestamp and source files
  3. Running in update mode presents a staleness report, accepts user approval for which sections to update, and regenerates only approved sections (not full documents)
  4. Approved inbox notes are expanded into proper prose matching the target document style and placed at classified locations
  5. OVERVIEW.md is generated after all audience docs complete and accurately routes readers to audience-specific documents
**Plans:** 2/2 plans executed

Plans:
- [x] 04-01-PLAN.md — Full create-docs-generate.md command: initial mode, update mode, 4-stage pipeline, notes integration
- [x] 04-02-PLAN.md — Install validation, test suite regression check, and road-runner smoke test

### Phase 5: Verify, Notes Command & Router
**Goal**: The verify step validates documentation quality, the add-docs command captures notes standalone, and the router ties the full pipeline together
**Depends on**: Phase 4
**Requirements**: VFY-01, VFY-02, VFY-03, VFY-04, VFY-05, VFY-06, VFY-07, CMD-01, CMD-04, CMD-05
**Success Criteria** (what must be TRUE):
  1. Running `/mg:create-docs-verify` produces `docs-verify-report.md` with issues categorized by severity covering reference integrity (file paths, symbols), cross-doc consistency (glossary terms), Diataxis mixing, completeness, example validity, and link integrity
  2. Running `/mg:add-docs "some note"` appends the note to `notes-inbox.json` with auto-classification (audience, document, section, confidence) and displays the classification for user correction
  3. Running `/mg:create-docs` detects pipeline state (no docs = initial creation, existing docs = update mode, partial scan = resume) and routes to the correct step automatically
  4. The complete pipeline (scan, generate, verify) can be run end-to-end via `/mg:create-docs` on a real project (road-runner) producing usable documentation
**Plans:** 2 plans

Plans:
- [x] 05-01-PLAN.md — Verify command and add-docs command: orchestrate verifier agent, standalone note capture
- [x] 05-02-PLAN.md — Router command and end-to-end pipeline validation on road-runner

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Infrastructure | 4/4 | Complete | 2026-03-16 |
| 2. Templates & Agent Definitions | 4/4 | Complete | 2026-03-16 |
| 3. Scan Pipeline | 2/2 | Complete | 2026-03-16 |
| 4. Generate Pipeline | 2/2 | Complete | 2026-03-16 |
| 5. Verify, Notes Command & Router | 2/2 | Complete | 2026-03-17 |
| 6. Fix Verify Feedback Loop & Scan Output | 3/4 | In Progress | - |

### Phase 6: Fix Verify Feedback Loop & Scan Output

**Goal:** Close the broken verify-generate feedback loop so verify findings flow back into generate as a 3rd approval tier, and replace direct LLM JSON writes in scan agents with a validation script
**Depends on:** Phase 5
**Requirements**: FIX-A1, FIX-A2, FIX-A3, FIX-A4, FIX-A5, FIX-A6, FIX-B1, FIX-B2, FIX-B3
**Success Criteria** (what must be TRUE):
  1. Verifier agent produces per-finding structured JSON entries via `add-verify-finding.py` and generates report from accumulated findings via `list-verify-findings.py`
  2. Generate command in update mode presents verify findings as 3rd approval tier (staleness -> findings -> notes) with unified 4-option approval and merged drill-in per document
  3. Router detects `docs-verify-findings.json` and routes user to re-run generate when findings are non-empty
  4. Scan agents use `write-scan-output.py` to validate output before writing to scan-logs
  5. All data flows through files (`--input`/`--output`), never through shell boundaries
**Plans:** 4 plans

Plans:
- [x] 06-01-PLAN.md — Python scripts: add-verify-finding, list-verify-findings, write-scan-output with tests
- [x] 06-02-PLAN.md — Agent rewrites: verifier.md two-step workflow, scan-audience.md output validation, schema.md update
- [x] 06-03-PLAN.md — Command updates: verify simplification, router findings-aware state, scan script-path passing
- [ ] 06-04-PLAN.md — Generate command: 3rd approval tier with merged drill-in and findings context for writers
