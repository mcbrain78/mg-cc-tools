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
- [ ] **Phase 7: Install Command** - Unified /mg:install tool management with discovery, status tracking, preflight, manifest, and interactive flow
- [ ] **Phase 8: Install Tool Improvements** - Two-stage install (install.sh + post-install.md subagent), tool discovery without install.sh, adopt via detect paths, execute-only tools
- [x] **Phase 9: Session Analyzer** - CLI query tool for navigating large CC session exports, stateless paginated commands, slash command with autonomous investigation (completed 2026-03-20)

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
  5. Agent definitions include instructions for parallel execution (one per audience + glossary concurrently)
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
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Infrastructure | 4/4 | Complete | 2026-03-16 |
| 2. Templates & Agent Definitions | 4/4 | Complete | 2026-03-16 |
| 3. Scan Pipeline | 2/2 | Complete | 2026-03-16 |
| 4. Generate Pipeline | 2/2 | Complete | 2026-03-16 |
| 5. Verify, Notes Command & Router | 2/2 | Complete | 2026-03-17 |
| 6. Fix Verify Feedback Loop & Scan Output | 3/4 | In Progress | - |
| 7. Install Command | 4/5 | In Progress|  |
| 8. Install Tool Improvements | 0/5 | Planned | - |
| 9. Session Analyzer | 3/4 | Complete    | 2026-03-20 |
| 10. Renderer for Install Command | 2/2 | Complete    | 2026-03-20 |
| 11. Add Tooling to Install Command | 3/3 | Complete    | 2026-03-20 |
| 12. Auto Doc Rename & Cleanup | 2/2 | Complete    | 2026-03-22 |

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

### Phase 7: Install Command

**Goal:** Build /mg:install -- a unified Claude Code slash command that installs, updates, and manages mg-cc-tools in target projects with dynamic tool discovery, staleness detection, preflight checks, LSP capability probing, manifest tracking, and migration support
**Depends on:** Phase 6
**Requirements**: INST-01, INST-02, INST-03, INST-04, INST-05, INST-06, INST-07, INST-08, INST-09, INST-10, INST-11, INST-12
**Success Criteria** (what must be TRUE):
  1. Running `mg-install-lib.py scan-status` discovers tools via tool.toml + install.sh scanning and reports 5 staleness states (Current, Update, Modified, Corrupt, Available)
  2. Running `mg-install-lib.py update-manifest` atomically writes tool entry with source checksums, commands, and version to the central manifest
  3. Running `mg-install-lib.py preflight` validates required/optional dependencies with fix instructions per platform
  4. Running `/mg:install` on a target project presents an interactive 8-step flow (target, status, action, preflight, probe, install, validate, summary)
  5. All 11 existing install.sh scripts call `mg-install-lib.py update-manifest` after every install -- no silent failures, no `|| true`
  6. Migration/adopt flow detects pre-manifest installations and builds manifest entries from current source checksums
**Plans:** 4/5 plans executed

Plans:
- [ ] 07-01-PLAN.md — Core Python script: mg-install-lib.py with 5 subcommands and full pytest suite (TDD)
- [ ] 07-02-PLAN.md — Tool metadata: tool.toml files for all 12 tool directories
- [ ] 07-03-PLAN.md — Slash command: install.md interactive flow and bootstrap install.sh
- [ ] 07-04-PLAN.md — Install.sh modifications: manifest update calls and python3 checks for all 11 scripts
- [ ] 07-05-PLAN.md — Integration validation: automated tests, bootstrap, and road-runner checkpoint

### Phase 8: Install Tool Improvements

**Goal:** Add two-stage install support to /mg:install: each tool can have an optional post-install.md that runs as a subagent after install.sh completes, enabling tools that need Claude Code intelligence for configuration (settings.json merges, interactive patch application) to be installed through the unified installer
**Depends on:** Phase 7
**Requirements**: INST-13, INST-14, INST-15, INST-16, INST-17, INST-18, INST-19, INST-20, INST-21, INST-22, INST-23, INST-24, INST-25, INST-26, INST-27, INST-28, INST-29, INST-30, INST-31, INST-32, INST-33, INST-34
**Success Criteria** (what must be TRUE):
  1. discover_tools() requires only tool.toml -- no install.sh needed for execute-only tools like gsd-patches
  2. scan-status output includes post_install and has_install_sh fields so install.md knows which pattern to use
  3. adopt_tools() detects pre-manifest installations via [detect].paths in addition to command presence
  4. /mg:install runs per-tool sequential with stop-on-error, spawning Agent subagents for post-install.md steps
  5. Three install patterns (copy-only, copy+configure, execute-only) work end-to-end through the unified installer
  6. permission-hooks, cc-regression-test, and gsd-patches each have self-contained post-install.md with status markers
  7. Snapshot files (.snapshot) no longer appear in Claude Code skill list (moved to tool-specific references/ directories)
**Plans:** 5 plans

Plans:
- [ ] 08-01-PLAN.md — mg-install-lib.py TDD: discover_tools, read_tool_toml, checksums, adopt, scan-status updates
- [ ] 08-02-PLAN.md — TEMPLATE-post-install.md + tool.toml updates for all 12 tools ([detect], [post_install], tiers)
- [ ] 08-03-PLAN.md — Per-tool changes: permission-hooks, cc-regression-test post-install.md + snapshot moves
- [ ] 08-04-PLAN.md — gsd-patches execute-only migration: post-install.md creation + install.sh deletion
- [ ] 08-05-PLAN.md — install.md rewrite: per-tool sequential, three patterns, subagent orchestration

### Phase 9: Session Analyzer

**Goal:** Build a stateless CLI query tool (cc_session_analyzer.py) that gives Claude selective access to CC session exports (up to 90MB+) through iterative paginated commands, paired with a /mg:analyze-session slash command that drives autonomous investigation
**Depends on:** Phase 8
**Requirements**: SAN-01, SAN-02, SAN-03, SAN-04, SAN-05, SAN-06, SAN-07, SAN-08, SAN-09, SAN-10, SAN-11, SAN-12, SAN-13, SAN-14, SAN-15, SAN-16, SAN-17, SAN-18, SAN-19, SAN-20, SAN-21, SAN-22, SAN-23, SAN-24
**Success Criteria** (what must be TRUE):
  1. Running `cc_session_analyzer.py <session.json>` produces a complete overview with metadata, timeline, orchestrator stats, agent stats, error list, heaviest agents, persisted outputs, and contextual commands
  2. All 8 commands work (overview, errors, flow, agent, agent-list, msg, search, export) with correct pagination and content display modes
  3. Error detection uses curated high-confidence patterns (is_error flag, tracebacks, exit codes) and filters noise patterns
  4. Agent-to-process linkage correctly maps orchestrator Agent calls to process entries via agentId
  5. Content commands (msg, errors, search) recover persisted output files, falling back to preview text when file is missing
  6. `/mg:analyze-session` slash command drives Claude through iterative analysis with dual mode (goal-directed and autonomous)
  7. Pytest suite passes with 1MB sample (default) and 75MB sample (--slow flag)
**Plans:** 4/4 plans complete

Plans:
- [ ] 09-01-PLAN.md — Test infrastructure, core data layer, error detection, pagination, and overview command
- [ ] 09-02-PLAN.md — Errors, flow, and agent-list commands with tests
- [ ] 09-03-PLAN.md — Agent deep dive, msg, and search commands with persisted recovery
- [ ] 09-04-PLAN.md — Export command, slash command, install.sh, and tool.toml delivery

### Phase 10: create a renderer for the install command

**Goal:** Move the install command's status table (Step 2) and tool picker (Step 3) rendering from LLM-generated output to deterministic Python subcommands in mg-install-lib.py, eliminating miscounted summaries, misaligned columns, and inconsistent tool picker formatting
**Requirements**: INST-35, INST-36, INST-37, INST-38, INST-39, INST-40, INST-41, INST-42
**Depends on:** Phase 9
**Plans:** 2/2 plans complete

Plans:
- [x] 10-01-PLAN.md — TDD: render-status-table, render-tool-picker, resolve-tool-selection subcommands with pytest
- [ ] 10-02-PLAN.md — install.md prompt simplification: replace inline templates with subcommand calls

### Phase 11: Add Tooling to Install Command

**Goal:** Refactor the install command from a 475-line LLM-driven state machine into a thin orchestrator where all deterministic logic (scenario selection, action mapping, install planning, result tracking, summary rendering) lives in Python subcommands, with one deliberate behavior change (Scenario B expanded to include corrupt/adopted statuses)
**Requirements**: INST-43, INST-44, INST-45, INST-46, INST-47, INST-48, INST-49, INST-50, INST-51, INST-52, INST-53, INST-54, INST-55, INST-56, INST-57
**Depends on:** Phase 10
**Plans:** 3/3 plans complete

Plans:
- [ ] 11-01-PLAN.md — TDD: _determine_scenario, render-action-menu, resolve-action, scan-status --auto-adopt
- [ ] 11-02-PLAN.md — TDD: get-install-plan, record-result, render-preflight, render-summary, render-validation, preflight --output
- [ ] 11-03-PLAN.md — install.md rewrite: thin orchestrator with consolidated rendering rule

### Phase 12: Auto Doc Rename & Cleanup

**Goal:** Rename the create-docs tool family to auto-doc and clean up dead code, orphaned agents, and latent bugs -- clearing the deck for all subsequent v1.1 work (phases 13-16)
**Requirements**: REN-01, REN-02, REN-03, REN-04, REN-05, REN-06, REN-07, FIX-C1, FIX-C2, FIX-C3, FIX-C4, FIX-C5
**Depends on:** Phase 11
**Plans:** 2/2 plans complete

Plans:
- [ ] 12-01-PLAN.md — Rename: directory move, file renames, bulk sed, explicit add-docs substitution, cross-tool updates, migration path, verification grep
- [ ] 12-02-PLAN.md — Bug fixes: staleness-check output wrapper, note_id field normalization, add-note stdout JSON, dead scan call removal, test updates

### Phase 13: Auto Doc Script Command

**Goal:** Add `/mg:auto-doc-script` -- a lightweight single-agent command that generates a README.AUTO-DOC.md for standalone scripts and small tool directories, without the full auto-doc pipeline
**Requirements**: SCRIPT-01, SCRIPT-02, SCRIPT-03, SCRIPT-04, SCRIPT-05, SCRIPT-06
**Depends on:** Phase 12
**Plans:** 1/1 plans complete

Plans:
- [ ] 13-01-PLAN.md — Command file, SCRIPT_README template, and install.sh COMMANDS array update

### Phase 14: auto doc reference manifest

**Goal:** Replace the lossy regex-based check-references.py with a structured manifest system where writer agents emit exact code symbols and file paths at generation time, and the verifier checks every entry deterministically via filesystem and LSP documentSymbol
**Requirements**: MAN-01, MAN-02, MAN-03, MAN-04, MAN-05, MAN-06, MAN-07, MAN-08, MAN-09, MAN-10, MAN-11, MAN-12
**Depends on:** Phase 13
**Plans:** 1/3 plans executed

Plans:
- [ ] 14-01-PLAN.md — TDD: add-manifest-entry.py script with tests, schema.md manifest format documentation
- [ ] 14-02-PLAN.md — Generate-side: manifest emission in 4 writer agents, manifest merge in generate orchestrator
- [ ] 14-03-PLAN.md — Verify-side: manifest-based Check 1 with LSP, delete check-references.py

### Phase 15: auto doc enduser quality

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 14
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd:plan-phase 15 to break down)

### Phase 16: auto doc incremental scan

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 15
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd:plan-phase 16 to break down)
