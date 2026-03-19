# Requirements: mg-cc-tools /mg:docs

**Defined:** 2026-03-15
**Core Value:** Automate the creation and maintenance of audience-specific documentation so it stays current as code evolves

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Commands

- [x] **CMD-01**: `/mg:create-docs` router detects pipeline state (no docs, existing docs, partial scan) and routes to correct step
- [x] **CMD-02**: `/mg:create-docs-scan` analyzes project and builds source material index mapping code files to document sections
- [x] **CMD-03**: `/mg:create-docs-generate` creates or updates documents section-by-section using templates and source material
- [x] **CMD-04**: `/mg:create-docs-verify` checks reference integrity, cross-doc consistency, Diataxis mixing, and completeness
- [x] **CMD-05**: `/mg:add-docs` captures a note to inbox with auto-classification (audience, document, section, confidence)

### Documents

- [x] **DOC-01**: Shared OVERVIEW.md generated as landing page with audience routing
- [x] **DOC-02**: Shared GLOSSARY.md generated as terminology source of truth
- [x] **DOC-03**: End-user USER_GUIDE.md with task-oriented how-to articles
- [ ] **DOC-04**: End-user domain-specific documents defined in project config
- [x] **DOC-05**: Developer ARCHITECTURE.md with system design, data model, ADRs
- [x] **DOC-06**: Developer DEVELOPER_GUIDE.md with code examples and extension patterns
- [x] **DOC-07**: Developer QUICK_REFERENCE.md as cheat sheet with paths, commands, lookups
- [x] **DOC-08**: Agent SYSTEM_MAP.md with component registry, file paths, API surface
- [x] **DOC-09**: Agent CONVENTIONS.md with code patterns, naming, do/don't rules
- [x] **DOC-10**: Agent GOTCHAS.md with edge cases, ordering constraints, invariants
- [x] **DOC-11**: Agent TESTING.md with test patterns, isolation, fixtures
- [x] **DOC-12**: DevOps OPERATIONS.md with deployment, service management, config
- [x] **DOC-13**: DevOps TROUBLESHOOTING.md with symptom-cause-fix runbook entries

### Templates

- [x] **TPL-01**: Three-layer template architecture: Diataxis classification + structural headings with purpose + exemplar per section
- [x] **TPL-02**: ~13 audience-organized templates in references/templates/ matching each document type
- [x] **TPL-03**: Optional section markers (prevent empty boilerplate in generated docs)

### Writer Agents

- [x] **AGT-01**: End-user writer agent with plain language, scannable formatting conventions
- [x] **AGT-02**: Developer writer agent with code-first, Stripe/Twilio-style conventions
- [x] **AGT-03**: Agent writer agent with explicit, machine-optimized conventions and YAML frontmatter
- [x] **AGT-04**: DevOps writer agent with runbook structure, copy-paste-ready commands
- [x] **AGT-05**: Glossary writer agent for terminology reconciliation across audiences
- [x] **AGT-06**: Staleness scanner agent for per-section freshness analysis
- [x] **AGT-07**: Verifier agent for cross-reference, Diataxis, and completeness checking
- [x] **AGT-08**: Writer agents run in parallel (one per audience + glossary)

### Scan

- [x] **SCN-01**: Project orientation: code structure, tech stack, entry points, deployment artifacts, existing docs
- [x] **SCN-02**: Source material index mapping code files to document sections
- [x] **SCN-03**: GSD context loading: phase SUMMARYs, REQUIREMENTS.md traceability, VERIFICATION.md gaps
- [x] **SCN-04**: Staleness detection: code-reference checks (file paths, symbol names exist in codebase)
- [x] **SCN-05**: Staleness detection: git-based section freshness (source files changed since section generated)
- [x] **SCN-06**: Notes inbox classification: pending notes assigned to audience, document, section
- [x] **SCN-07**: Gap analysis: code components without documentation for each audience
- [x] **SCN-08**: Output as docs-scan.json shared data contract

### Generate

- [x] **GEN-01**: Initial mode: section-by-section generation following three-layer templates with source material
- [x] **GEN-02**: Update mode: staleness report presented, user approves which sections to update
- [x] **GEN-03**: Notes integration: approved inbox notes expanded and placed at classified locations
- [x] **GEN-04**: Section ownership tracking via docs-meta HTML comments (last-updated, sources)
- [x] **GEN-05**: Cross-document consistency: writers receive glossary, new terms proposed for addition
- [x] **GEN-06**: OVERVIEW.md generated last (after all audience docs complete) for accurate routing

### Verify

- [x] **VFY-01**: Reference integrity: file paths, symbol names, commands in docs verified against codebase
- [x] **VFY-02**: Cross-doc consistency: terms match glossary, descriptions match across audiences
- [x] **VFY-03**: Diataxis mixing detection: flag tutorial content in reference docs, explanation in how-to
- [x] **VFY-04**: Completeness: major code components have documentation for each relevant audience
- [x] **VFY-05**: Example validity: code examples are syntactically valid
- [x] **VFY-06**: Link integrity: internal markdown links between docs resolve
- [x] **VFY-07**: Output as docs-verify-report.md with issues by severity

### Infrastructure

- [x] **INF-01**: Python script: add-note.py (atomic append to notes-inbox.json)
- [x] **INF-02**: Python script: classify-note.py (deterministic heuristics for note classification)
- [x] **INF-03**: Python script: check-references.py (verify file paths and symbol names in docs exist)
- [x] **INF-04**: Python script: merge-scan.py (merge per-audience scan results into docs-scan.json)
- [x] **INF-05**: Python script: staleness-check.py (git-based section freshness analysis)
- [x] **INF-06**: Schema definition: docs-scan.json format in references/schema.md
- [x] **INF-07**: Style guide: cross-audience writing conventions in references/style-guide.md
- [x] **INF-08**: install.sh with --project, --global, --target modes and sed path resolution
- [x] **INF-09**: Project scaffolding: .mg/docs/ with config, empty inbox, scan-logs directory
- [x] **INF-10**: Config: .docs.config.json with audience enable/disable, custom documents, docs_dir override

### Install Tool Improvements

- [x] **INST-13**: discover_tools() requires only tool.toml — no install.sh needed for tool discovery
- [x] **INST-14**: read_tool_toml() parses [post_install] and [detect] sections from tool.toml
- [x] **INST-15**: compute_tool_checksums() includes post-install.md and patches/**/*.md in checksum scope
- [x] **INST-16**: adopt_tools() detects pre-manifest installations via [detect].paths in addition to command presence
- [x] **INST-17**: scan_status() reports post_install and has_install_sh fields for install pattern determination
- [x] **INST-18**: TEMPLATE-post-install.md defines mandatory POST-INSTALL: SUCCESS/FAILED status marker pattern
- [x] **INST-19**: Six tools have [detect] sections in tool.toml for adopt detection paths
- [x] **INST-20**: Tool tier changes: permission-hooks, gsd-patches, mg-gsd-wrappers set to standard = false
- [x] **INST-21**: permission-hooks has self-contained post-install.md for settings.json hook configuration
- [x] **INST-22**: cc-regression-test has self-contained post-install.md for settings.json hook merge
- [x] **INST-23**: gsd-patches has execute-only post-install.md for GSD patch application from source
- [x] **INST-24**: gsd-patches operates as execute-only tool (no install.sh, post-install.md only)
- [x] **INST-25**: mg-gsd-wrappers snapshot moved from commands/mg/ to references/ directory
- [x] **INST-26**: create-context snapshot moved from commands/mg/ to references/ directory
- [x] **INST-27**: Stale file cleanup in install.sh/post-install.md for permission-hooks and gsd-patches
- [x] **INST-28**: install.md runs per-tool sequential (replaces batch execution)
- [x] **INST-29**: install.md stops on first failure (replaces continue-on-error)
- [x] **INST-30**: install.md spawns Agent subagents for post-install.md execution
- [x] **INST-31**: install.md parses POST-INSTALL: SUCCESS/FAILED from subagent return text
- [x] **INST-32**: install.md handles execute-only pattern (skip install.sh, call update-manifest directly)
- [x] **INST-33**: install.md adopt checks [detect].paths and skips execute-only tools
- [x] **INST-34**: install.md status table reflects updated tier settings (gsd-patches optional, not excluded)

### Session Analyzer

- [ ] **SAN-01**: `cc_session_compactor.py` renamed from `reduce_cc_session_export.py` with all existing functionality preserved (levels 0-5, l2-compact)
- [ ] **SAN-02**: `cc_session_analyzer.py` loads session JSON via `json.load()` and drops `chunks` data before processing
- [ ] **SAN-03**: Default command (`overview`) produces session summary with metadata, timeline, orchestrator stats, agent stats, error list, heaviest agents, persisted outputs, and contextual next-step commands
- [ ] **SAN-04**: `errors` command shows all detected errors with context (agent prompt snippet, failing tool call, surrounding text), paginated
- [ ] **SAN-05**: `flow` command produces orchestrator decision trace with one line per message using mechanical classification rules and timestamps, paginated
- [ ] **SAN-06**: `agent <id-prefix>` command shows single agent deep dive with tool calls and reasoning interleaved in execution order, paginated
- [ ] **SAN-07**: `agent-list` command shows one line per agent (ID, status, duration, tools, size, prompt summary), paginated
- [ ] **SAN-08**: `msg` command shows single message with ±2 context messages and full content, supports both `msg <N>` and `msg <agent-prefix> <N>` forms
- [ ] **SAN-09**: `search <pattern>` command searches tool inputs, results (with persisted file recovery), and assistant text, paginated
- [ ] **SAN-10**: `export` command delegates to compactor after dropping chunks, supports `--level` flag
- [ ] **SAN-11**: Pagination with `--offset N`, `--limit N`, `--all` flags and footer showing item count and exact copy-paste next command
- [ ] **SAN-12**: Error detection uses curated high-confidence patterns: `is_error` flag, Python tracebacks, bash exit codes, and agent result status patterns
- [ ] **SAN-13**: Error detection filters noise patterns (`exceeds maximum allowed tokens`, `File has not been read yet`, `File does not exist`) from error counts
- [ ] **SAN-14**: Agent-to-process linkage parses `agentId` from tool_result messages to connect orchestrator Agent calls to process entries with duration
- [ ] **SAN-15**: Content commands (`msg`, `errors`, `search`) recover persisted output files from extracted paths, falling back to preview text when file is missing
- [ ] **SAN-16**: Ambiguous agent prefix lists matching agents and exits with guidance to use a longer prefix
- [ ] **SAN-17**: Search scope filters: `--scope orchestrator`, `--scope agents`, `--scope agent:<prefix>`, default searches everything
- [ ] **SAN-18**: All output is plain text — no ANSI color codes
- [ ] **SAN-19**: `/mg:analyze-session` slash command with tool.toml and install.sh following mg-cc-tools conventions
- [ ] **SAN-20**: Slash command dual mode: goal-directed investigation when user provides a question, autonomous analysis when no goal given
- [ ] **SAN-21**: Pytest suite with 1MB sample tests (default) and 75MB sample tests (`@pytest.mark.slow`, `--slow` flag)
- [ ] **SAN-22**: Analyzer imports `cc_session_compactor` for export command but implements independent error detection
- [ ] **SAN-23**: Overview contextual commands section omits irrelevant commands based on session content (e.g., no `agent-list` if no agents)
- [ ] **SAN-24**: Summary commands (`overview`, `flow`, `agent`, `agent-list`) show metadata only; content commands (`msg`, `errors`, `search`) show full content with persisted recovery

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Staleness Advanced

- **STL-01**: Schema drift detection (compare documented DB schemas, API contracts against actual source)
- **STL-02**: Terminology drift detection (glossary terms match actual usage in code and docs)
- **STL-03**: GSD deviation signals (phase SUMMARYs with deviations flag sections needing updates)

### Backlog Integration

- **BKL-01**: Documentation gaps found by verify step optionally added to .planning/BACKLOG.md as documentation debt

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-push to hosting (GitHub Pages, ReadTheDocs) | Deployment is outside tool scope |
| Image/diagram generation | LLMs can't produce images; ASCII diagrams only |
| Non-Markdown output (PDF, HTML) | Markdown is the universal format |
| Real-time sync (file watchers, CI hooks) | Run-on-demand via slash commands |
| Multi-language documentation (i18n) | English only for v1 |
| Custom document template authoring UI | Users edit template .md files directly |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CMD-01 | Phase 5 | Complete |
| CMD-02 | Phase 3 | Complete |
| CMD-03 | Phase 4 | Complete |
| CMD-04 | Phase 5 | Complete |
| CMD-05 | Phase 5 | Complete |
| DOC-01 | Phase 4 | Complete |
| DOC-02 | Phase 4 | Complete |
| DOC-03 | Phase 4 | Complete |
| DOC-04 | Phase 4 | Pending |
| DOC-05 | Phase 4 | Complete |
| DOC-06 | Phase 4 | Complete |
| DOC-07 | Phase 4 | Complete |
| DOC-08 | Phase 4 | Complete |
| DOC-09 | Phase 4 | Complete |
| DOC-10 | Phase 4 | Complete |
| DOC-11 | Phase 4 | Complete |
| DOC-12 | Phase 4 | Complete |
| DOC-13 | Phase 4 | Complete |
| TPL-01 | Phase 2 | Complete |
| TPL-02 | Phase 2 | Complete |
| TPL-03 | Phase 2 | Complete |
| AGT-01 | Phase 2 | Complete |
| AGT-02 | Phase 2 | Complete |
| AGT-03 | Phase 2 | Complete |
| AGT-04 | Phase 2 | Complete |
| AGT-05 | Phase 2 | Complete |
| AGT-06 | Phase 2 | Complete |
| AGT-07 | Phase 2 | Complete |
| AGT-08 | Phase 2 | Complete |
| SCN-01 | Phase 3 | Complete |
| SCN-02 | Phase 3 | Complete |
| SCN-03 | Phase 3 | Complete |
| SCN-04 | Phase 3 | Complete |
| SCN-05 | Phase 3 | Complete |
| SCN-06 | Phase 3 | Complete |
| SCN-07 | Phase 3 | Complete |
| SCN-08 | Phase 3 | Complete |
| GEN-01 | Phase 4 | Complete |
| GEN-02 | Phase 4 | Complete |
| GEN-03 | Phase 4 | Complete |
| GEN-04 | Phase 4 | Complete |
| GEN-05 | Phase 4 | Complete |
| GEN-06 | Phase 4 | Complete |
| VFY-01 | Phase 5 | Complete |
| VFY-02 | Phase 5 | Complete |
| VFY-03 | Phase 5 | Complete |
| VFY-04 | Phase 5 | Complete |
| VFY-05 | Phase 5 | Complete |
| VFY-06 | Phase 5 | Complete |
| VFY-07 | Phase 5 | Complete |
| INF-01 | Phase 1 | Complete |
| INF-02 | Phase 1 | Complete |
| INF-03 | Phase 1 | Complete |
| INF-04 | Phase 1 | Complete |
| INF-05 | Phase 1 | Complete |
| INF-06 | Phase 1 | Complete |
| INF-07 | Phase 1 | Complete |
| INF-08 | Phase 1 | Complete |
| INF-09 | Phase 1 | Complete |
| INF-10 | Phase 1 | Complete |
| INST-13 | Phase 8 | Complete |
| INST-14 | Phase 8 | Complete |
| INST-15 | Phase 8 | Complete |
| INST-16 | Phase 8 | Complete |
| INST-17 | Phase 8 | Complete |
| INST-18 | Phase 8 | Complete |
| INST-19 | Phase 8 | Complete |
| INST-20 | Phase 8 | Complete |
| INST-21 | Phase 8 | Complete |
| INST-22 | Phase 8 | Complete |
| INST-23 | Phase 8 | Complete |
| INST-24 | Phase 8 | Complete |
| INST-25 | Phase 8 | Complete |
| INST-26 | Phase 8 | Complete |
| INST-27 | Phase 8 | Complete |
| INST-28 | Phase 8 | Complete |
| INST-29 | Phase 8 | Complete |
| INST-30 | Phase 8 | Complete |
| INST-31 | Phase 8 | Complete |
| INST-32 | Phase 8 | Complete |
| INST-33 | Phase 8 | Complete |
| INST-34 | Phase 8 | Complete |
| SAN-01 | Phase 9 | Pending |
| SAN-02 | Phase 9 | Pending |
| SAN-03 | Phase 9 | Pending |
| SAN-04 | Phase 9 | Pending |
| SAN-05 | Phase 9 | Pending |
| SAN-06 | Phase 9 | Pending |
| SAN-07 | Phase 9 | Pending |
| SAN-08 | Phase 9 | Pending |
| SAN-09 | Phase 9 | Pending |
| SAN-10 | Phase 9 | Pending |
| SAN-11 | Phase 9 | Pending |
| SAN-12 | Phase 9 | Pending |
| SAN-13 | Phase 9 | Pending |
| SAN-14 | Phase 9 | Pending |
| SAN-15 | Phase 9 | Pending |
| SAN-16 | Phase 9 | Pending |
| SAN-17 | Phase 9 | Pending |
| SAN-18 | Phase 9 | Pending |
| SAN-19 | Phase 9 | Pending |
| SAN-20 | Phase 9 | Pending |
| SAN-21 | Phase 9 | Pending |
| SAN-22 | Phase 9 | Pending |
| SAN-23 | Phase 9 | Pending |
| SAN-24 | Phase 9 | Pending |

**Coverage:**
- v1 requirements: 106 total
- Mapped to phases: 106
- Unmapped: 0

---
*Requirements defined: 2026-03-15*
*Last updated: 2026-03-19 after Phase 9 requirement generation*
