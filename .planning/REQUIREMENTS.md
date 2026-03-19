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

- [x] **LIB-DISCOVER**: discover_tools() requires only tool.toml — no install.sh needed for tool discovery
- [x] **LIB-TOML**: read_tool_toml() parses [post_install] and [detect] sections from tool.toml
- [x] **LIB-CHECKSUMS**: compute_tool_checksums() includes post-install.md and patches/**/*.md in checksum scope
- [x] **LIB-ADOPT**: adopt_tools() detects pre-manifest installations via [detect].paths in addition to command presence
- [x] **LIB-SCANSTATUS**: scan_status() reports post_install and has_install_sh fields for install pattern determination
- [x] **TEMPLATE**: TEMPLATE-post-install.md defines mandatory POST-INSTALL: SUCCESS/FAILED status marker pattern
- [x] **DETECT**: Six tools have [detect] sections in tool.toml for adopt detection paths
- [x] **TIERS**: Tool tier changes: permission-hooks, gsd-patches, mg-gsd-wrappers set to standard = false
- [x] **POSTINSTALL-PERMHOOKS**: permission-hooks has self-contained post-install.md for settings.json hook configuration
- [x] **POSTINSTALL-CCREGTEST**: cc-regression-test has self-contained post-install.md for settings.json hook merge
- [x] **POSTINSTALL-GSDPATCHES**: gsd-patches has execute-only post-install.md for GSD patch application from source
- [x] **EXECUTEONLY**: gsd-patches operates as execute-only tool (no install.sh, post-install.md only)
- [x] **SNAPSHOT-MGWRAPPERS**: mg-gsd-wrappers snapshot moved from commands/mg/ to references/ directory
- [x] **SNAPSHOT-CREATECTX**: create-context snapshot moved from commands/mg/ to references/ directory
- [x] **STALE-CLEANUP**: Stale file cleanup in install.sh/post-install.md for permission-hooks and gsd-patches
- [x] **INSTALL-SEQUENTIAL**: install.md runs per-tool sequential (replaces batch execution)
- [x] **INSTALL-STOPONERROR**: install.md stops on first failure (replaces continue-on-error)
- [x] **INSTALL-SUBAGENT**: install.md spawns Agent subagents for post-install.md execution
- [x] **INSTALL-STATUSMARKER**: install.md parses POST-INSTALL: SUCCESS/FAILED from subagent return text
- [x] **INSTALL-EXECUTEONLY**: install.md handles execute-only pattern (skip install.sh, call update-manifest directly)
- [x] **INSTALL-ADOPT**: install.md adopt checks [detect].paths and skips execute-only tools
- [x] **INSTALL-TIERS**: install.md status table reflects updated tier settings (gsd-patches optional, not excluded)

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
| LIB-DISCOVER | Phase 8 | Complete |
| LIB-TOML | Phase 8 | Complete |
| LIB-CHECKSUMS | Phase 8 | Complete |
| LIB-ADOPT | Phase 8 | Complete |
| LIB-SCANSTATUS | Phase 8 | Complete |
| TEMPLATE | Phase 8 | Complete |
| DETECT | Phase 8 | Complete |
| TIERS | Phase 8 | Complete |
| POSTINSTALL-PERMHOOKS | Phase 8 | Complete |
| POSTINSTALL-CCREGTEST | Phase 8 | Complete |
| POSTINSTALL-GSDPATCHES | Phase 8 | Complete |
| EXECUTEONLY | Phase 8 | Complete |
| SNAPSHOT-MGWRAPPERS | Phase 8 | Complete |
| SNAPSHOT-CREATECTX | Phase 8 | Complete |
| STALE-CLEANUP | Phase 8 | Complete |
| INSTALL-SEQUENTIAL | Phase 8 | Complete |
| INSTALL-STOPONERROR | Phase 8 | Complete |
| INSTALL-SUBAGENT | Phase 8 | Complete |
| INSTALL-STATUSMARKER | Phase 8 | Complete |
| INSTALL-EXECUTEONLY | Phase 8 | Complete |
| INSTALL-ADOPT | Phase 8 | Complete |
| INSTALL-TIERS | Phase 8 | Complete |

**Coverage:**
- v1 requirements: 82 total
- Mapped to phases: 82
- Unmapped: 0

---
*Requirements defined: 2026-03-15*
*Last updated: 2026-03-19 after Phase 8 completion (install tool improvements traceability added)*
