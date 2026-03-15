# Requirements: mg-cc-tools /mg:docs

**Defined:** 2026-03-15
**Core Value:** Automate the creation and maintenance of audience-specific documentation so it stays current as code evolves

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Commands

- [ ] **CMD-01**: `/mg:create-docs` router detects pipeline state (no docs, existing docs, partial scan) and routes to correct step
- [ ] **CMD-02**: `/mg:create-docs-scan` analyzes project and builds source material index mapping code files to document sections
- [ ] **CMD-03**: `/mg:create-docs-generate` creates or updates documents section-by-section using templates and source material
- [ ] **CMD-04**: `/mg:create-docs-verify` checks reference integrity, cross-doc consistency, Diataxis mixing, and completeness
- [ ] **CMD-05**: `/mg:add-docs` captures a note to inbox with auto-classification (audience, document, section, confidence)

### Documents

- [ ] **DOC-01**: Shared OVERVIEW.md generated as landing page with audience routing
- [ ] **DOC-02**: Shared GLOSSARY.md generated as terminology source of truth
- [ ] **DOC-03**: End-user USER_GUIDE.md with task-oriented how-to articles
- [ ] **DOC-04**: End-user domain-specific documents defined in project config
- [ ] **DOC-05**: Developer ARCHITECTURE.md with system design, data model, ADRs
- [ ] **DOC-06**: Developer DEVELOPER_GUIDE.md with code examples and extension patterns
- [ ] **DOC-07**: Developer QUICK_REFERENCE.md as cheat sheet with paths, commands, lookups
- [ ] **DOC-08**: Agent SYSTEM_MAP.md with component registry, file paths, API surface
- [ ] **DOC-09**: Agent CONVENTIONS.md with code patterns, naming, do/don't rules
- [ ] **DOC-10**: Agent GOTCHAS.md with edge cases, ordering constraints, invariants
- [ ] **DOC-11**: Agent TESTING.md with test patterns, isolation, fixtures
- [ ] **DOC-12**: DevOps OPERATIONS.md with deployment, service management, config
- [ ] **DOC-13**: DevOps TROUBLESHOOTING.md with symptom-cause-fix runbook entries

### Templates

- [ ] **TPL-01**: Three-layer template architecture: Diataxis classification + structural headings with purpose + exemplar per section
- [ ] **TPL-02**: ~13 audience-organized templates in references/templates/ matching each document type
- [ ] **TPL-03**: Optional section markers (prevent empty boilerplate in generated docs)

### Writer Agents

- [ ] **AGT-01**: End-user writer agent with plain language, scannable formatting conventions
- [ ] **AGT-02**: Developer writer agent with code-first, Stripe/Twilio-style conventions
- [ ] **AGT-03**: Agent writer agent with explicit, machine-optimized conventions and YAML frontmatter
- [ ] **AGT-04**: DevOps writer agent with runbook structure, copy-paste-ready commands
- [ ] **AGT-05**: Glossary writer agent for terminology reconciliation across audiences
- [ ] **AGT-06**: Staleness scanner agent for per-section freshness analysis
- [ ] **AGT-07**: Verifier agent for cross-reference, Diataxis, and completeness checking
- [ ] **AGT-08**: Writer agents run in parallel (one per audience + glossary)

### Scan

- [ ] **SCN-01**: Project orientation: code structure, tech stack, entry points, deployment artifacts, existing docs
- [ ] **SCN-02**: Source material index mapping code files to document sections
- [ ] **SCN-03**: GSD context loading: phase SUMMARYs, REQUIREMENTS.md traceability, VERIFICATION.md gaps
- [ ] **SCN-04**: Staleness detection: code-reference checks (file paths, symbol names exist in codebase)
- [ ] **SCN-05**: Staleness detection: git-based section freshness (source files changed since section generated)
- [ ] **SCN-06**: Notes inbox classification: pending notes assigned to audience, document, section
- [ ] **SCN-07**: Gap analysis: code components without documentation for each audience
- [ ] **SCN-08**: Output as docs-scan.json shared data contract

### Generate

- [ ] **GEN-01**: Initial mode: section-by-section generation following three-layer templates with source material
- [ ] **GEN-02**: Update mode: staleness report presented, user approves which sections to update
- [ ] **GEN-03**: Notes integration: approved inbox notes expanded and placed at classified locations
- [ ] **GEN-04**: Section ownership tracking via docs-meta HTML comments (last-updated, sources)
- [ ] **GEN-05**: Cross-document consistency: writers receive glossary, new terms proposed for addition
- [ ] **GEN-06**: OVERVIEW.md generated last (after all audience docs complete) for accurate routing

### Verify

- [ ] **VFY-01**: Reference integrity: file paths, symbol names, commands in docs verified against codebase
- [ ] **VFY-02**: Cross-doc consistency: terms match glossary, descriptions match across audiences
- [ ] **VFY-03**: Diataxis mixing detection: flag tutorial content in reference docs, explanation in how-to
- [ ] **VFY-04**: Completeness: major code components have documentation for each relevant audience
- [ ] **VFY-05**: Example validity: code examples are syntactically valid
- [ ] **VFY-06**: Link integrity: internal markdown links between docs resolve
- [ ] **VFY-07**: Output as docs-verify-report.md with issues by severity

### Infrastructure

- [ ] **INF-01**: Python script: add-note.py (atomic append to notes-inbox.json)
- [ ] **INF-02**: Python script: classify-note.py (deterministic heuristics for note classification)
- [ ] **INF-03**: Python script: check-references.py (verify file paths and symbol names in docs exist)
- [ ] **INF-04**: Python script: merge-scan.py (merge per-audience scan results into docs-scan.json)
- [ ] **INF-05**: Python script: staleness-check.py (git-based section freshness analysis)
- [ ] **INF-06**: Schema definition: docs-scan.json format in references/schema.md
- [ ] **INF-07**: Style guide: cross-audience writing conventions in references/style-guide.md
- [ ] **INF-08**: install.sh with --project, --global, --target modes and sed path resolution
- [ ] **INF-09**: Project scaffolding: .mg/docs/ with config, empty inbox, scan-logs directory
- [ ] **INF-10**: Config: .docs.config.json with audience enable/disable, custom documents, docs_dir override

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
| CMD-01 | Phase 5 | Pending |
| CMD-02 | Phase 3 | Pending |
| CMD-03 | Phase 4 | Pending |
| CMD-04 | Phase 5 | Pending |
| CMD-05 | Phase 5 | Pending |
| DOC-01 | Phase 4 | Pending |
| DOC-02 | Phase 4 | Pending |
| DOC-03 | Phase 4 | Pending |
| DOC-04 | Phase 4 | Pending |
| DOC-05 | Phase 4 | Pending |
| DOC-06 | Phase 4 | Pending |
| DOC-07 | Phase 4 | Pending |
| DOC-08 | Phase 4 | Pending |
| DOC-09 | Phase 4 | Pending |
| DOC-10 | Phase 4 | Pending |
| DOC-11 | Phase 4 | Pending |
| DOC-12 | Phase 4 | Pending |
| DOC-13 | Phase 4 | Pending |
| TPL-01 | Phase 2 | Pending |
| TPL-02 | Phase 2 | Pending |
| TPL-03 | Phase 2 | Pending |
| AGT-01 | Phase 2 | Pending |
| AGT-02 | Phase 2 | Pending |
| AGT-03 | Phase 2 | Pending |
| AGT-04 | Phase 2 | Pending |
| AGT-05 | Phase 2 | Pending |
| AGT-06 | Phase 2 | Pending |
| AGT-07 | Phase 2 | Pending |
| AGT-08 | Phase 2 | Pending |
| SCN-01 | Phase 3 | Pending |
| SCN-02 | Phase 3 | Pending |
| SCN-03 | Phase 3 | Pending |
| SCN-04 | Phase 3 | Pending |
| SCN-05 | Phase 3 | Pending |
| SCN-06 | Phase 3 | Pending |
| SCN-07 | Phase 3 | Pending |
| SCN-08 | Phase 3 | Pending |
| GEN-01 | Phase 4 | Pending |
| GEN-02 | Phase 4 | Pending |
| GEN-03 | Phase 4 | Pending |
| GEN-04 | Phase 4 | Pending |
| GEN-05 | Phase 4 | Pending |
| GEN-06 | Phase 4 | Pending |
| VFY-01 | Phase 5 | Pending |
| VFY-02 | Phase 5 | Pending |
| VFY-03 | Phase 5 | Pending |
| VFY-04 | Phase 5 | Pending |
| VFY-05 | Phase 5 | Pending |
| VFY-06 | Phase 5 | Pending |
| VFY-07 | Phase 5 | Pending |
| INF-01 | Phase 1 | Pending |
| INF-02 | Phase 1 | Pending |
| INF-03 | Phase 1 | Pending |
| INF-04 | Phase 1 | Pending |
| INF-05 | Phase 1 | Pending |
| INF-06 | Phase 1 | Pending |
| INF-07 | Phase 1 | Pending |
| INF-08 | Phase 1 | Pending |
| INF-09 | Phase 1 | Pending |
| INF-10 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 60 total
- Mapped to phases: 60
- Unmapped: 0

---
*Requirements defined: 2026-03-15*
*Last updated: 2026-03-15 after roadmap creation (traceability added)*
