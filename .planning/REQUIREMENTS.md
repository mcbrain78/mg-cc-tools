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

### Install Rendering

- [x] **INST-35**: Running `mg-install-lib.py render-status-table` with scan-status JSON produces a formatted three-tier status table on stdout
- [x] **INST-36**: Running `mg-install-lib.py render-tool-picker` with scan-status JSON produces a numbered tool list on stdout with section headers
- [x] **INST-37**: Running `mg-install-lib.py resolve-tool-selection` with scan-status JSON and user text produces a JSON list of resolved tool names
- [x] **INST-38**: render-tool-picker and resolve-tool-selection share a single internal ordering function (standard-first, then optional, excluding excluded)
- [x] **INST-39**: install.md Step 2 calls render-status-table and displays output verbatim, replacing the inline template
- [x] **INST-40**: install.md Step 3 uses render-tool-picker and resolve-tool-selection for the "Select specific tools" sub-flow
- [x] **INST-41**: Scenario A/B/C top-level action menus remain LLM-rendered (not moved to Python)
- [x] **INST-42**: Pytest tests cover all three new subcommands (render-status-table, render-tool-picker, resolve-tool-selection)

### Install Orchestration

- [x] **INST-43**: `scan-status` gains an `--auto-adopt` flag that auto-detects and adopts existing installations when no manifest exists, reporting adopted tools in its output
- [x] **INST-44**: `render-action-menu` subcommand produces the correct scenario menu as plain text given scan-status JSON input
- [x] **INST-45**: `resolve-action` subcommand maps a user's menu selection to an action and tool list given scan-status JSON and the user's response
- [x] **INST-46**: `get-install-plan` subcommand produces a JSON install plan with per-tool install pattern, expected action, install command, and command filenames
- [x] **INST-47**: `render-preflight` subcommand formats preflight results from JSON into human-readable output (existing `preflight` subcommand gains `--output` support)
- [x] **INST-48**: `record-result` subcommand appends per-tool success or failure to an install-results JSON file, deriving action and command filenames from the install plan
- [x] **INST-49**: `render-summary` subcommand formats the final summary table from install results, scan-status, and optional preflight capability data
- [x] **INST-50**: `render-validation` subcommand formats validation results from JSON into human-readable PASS/WARNING output
- [x] **INST-51**: Scenario B now triggers on corrupt and adopted statuses in addition to update and modified (behavior change from v1.2)
- [x] **INST-52**: `install.md` prompt is rewritten as a thin orchestrator where the LLM only echoes output, collects input, and spawns agents — no conditional rendering or scenario logic in the prompt
- [x] **INST-53**: `render-action-menu` and `resolve-action` share a single `_determine_scenario()` function to prevent scenario drift
- [x] **INST-54**: All `render-*` subcommand output is echoed verbatim as fenced code blocks; other subcommand output is machine-readable JSON not echoed (single consolidated rendering rule)
- [x] **INST-55**: All subcommands reading scan-status use `--input <path>`; `render-summary` uses `--input`, `--results`, `--preflight` for its three inputs
- [x] **INST-56**: Inter-step temp files use per-target subdirectories (`/tmp/mg-install-<target-basename>/`) to prevent collision across concurrent sessions
- [x] **INST-57**: All new code is stdlib-only with no pip dependencies

### Session Analyzer

- [x] **SAN-01**: `cc_session_compactor.py` renamed from `reduce_cc_session_export.py` with all existing functionality preserved (levels 0-5, l2-compact)
- [x] **SAN-02**: `cc_session_analyzer.py` loads session JSON via `json.load()` and drops `chunks` data before processing
- [x] **SAN-03**: Default command (`overview`) produces session summary with metadata, timeline, orchestrator stats, agent stats, error list, heaviest agents, persisted outputs, and contextual next-step commands
- [x] **SAN-04**: `errors` command shows all detected errors with context (agent prompt snippet, failing tool call, surrounding text), paginated
- [x] **SAN-05**: `flow` command produces orchestrator decision trace with one line per message using mechanical classification rules and timestamps, paginated
- [x] **SAN-06**: `agent <id-prefix>` command shows single agent deep dive with tool calls and reasoning interleaved in execution order, paginated
- [x] **SAN-07**: `agent-list` command shows one line per agent (ID, status, duration, tools, size, prompt summary), paginated
- [x] **SAN-08**: `msg` command shows single message with ±2 context messages and full content, supports both `msg <N>` and `msg <agent-prefix> <N>` forms
- [x] **SAN-09**: `search <pattern>` command searches tool inputs, results (with persisted file recovery), and assistant text, paginated
- [x] **SAN-10**: `export` command delegates to compactor after dropping chunks, supports `--level` flag
- [x] **SAN-11**: Pagination with `--offset N`, `--limit N`, `--all` flags and footer showing item count and exact copy-paste next command
- [x] **SAN-12**: Error detection uses curated high-confidence patterns: `is_error` flag, Python tracebacks, bash exit codes, and agent result status patterns
- [x] **SAN-13**: Error detection filters noise patterns (`exceeds maximum allowed tokens`, `File has not been read yet`, `File does not exist`) from error counts
- [x] **SAN-14**: Agent-to-process linkage parses `agentId` from tool_result messages to connect orchestrator Agent calls to process entries with duration
- [x] **SAN-15**: Content commands (`msg`, `errors`, `search`) recover persisted output files from extracted paths, falling back to preview text when file is missing
- [x] **SAN-16**: Ambiguous agent prefix lists matching agents and exits with guidance to use a longer prefix
- [x] **SAN-17**: Search scope filters: `--scope orchestrator`, `--scope agents`, `--scope agent:<prefix>`, default searches everything
- [x] **SAN-18**: All output is plain text — no ANSI color codes
- [x] **SAN-19**: `/mg:analyze-session` slash command with tool.toml and install.sh following mg-cc-tools conventions
- [x] **SAN-20**: Slash command dual mode: goal-directed investigation when user provides a question, autonomous analysis when no goal given
- [x] **SAN-21**: Pytest suite with 1MB sample tests (default) and 75MB sample tests (`@pytest.mark.slow`, `--slow` flag)
- [x] **SAN-22**: Analyzer imports `cc_session_compactor` for export command but implements independent error detection
- [x] **SAN-23**: Overview contextual commands section omits irrelevant commands based on session content (e.g., no `agent-list` if no agents)
- [x] **SAN-24**: Summary commands (`overview`, `flow`, `agent`, `agent-list`) show metadata only; content commands (`msg`, `errors`, `search`) show full content with persisted recovery

### Auto Doc Rename & Cleanup

- [x] **REN-01**: `create-docs/` directory renamed to `auto-doc/` with all 5 command files renamed per the command rename map
- [x] **REN-02**: Bulk `s/create-docs/auto-doc/g` substitution applied to all non-historical files under `auto-doc/`
- [x] **REN-03**: Explicit `s/add-docs/auto-doc-add/g` substitution applied to all non-trivial locations (generate command HTML comments, add command self-references, router references)
- [x] **REN-04**: Cross-tool references updated in mg-install-lib.py workspace mapping, install.md tool listing (both copies), and permission-hooks test data
- [x] **REN-05**: Migration path in `auto-doc/install.sh` detects old `create-docs` installation, removes stale files and commands, cleans manifest entry
- [x] **REN-06**: Orphaned `staleness-scanner.md` agent deleted (never wired into any command, references non-existent parameters)
- [x] **REN-07**: Verification grep confirms zero `create-docs` or `add-docs` references outside `.planning/` and `docs/work-queue/` exclusion directories
- [x] **FIX-C1**: Dead `check-references.py` invocation removed from scan pipeline Step 3 (reference checking is a verify concern, not scan)
- [x] **FIX-C2**: `staleness-check.py` CLI output wrapped in `{"staleness_report": entries}` dict for `merge-scan.py` compatibility
- [x] **FIX-C3**: `note_id` field used consistently in `add-note.py` and `classify-note.py` (replacing `id`), matching schema contract
- [x] **FIX-C4**: `add-note.py` outputs JSON `{"note_id": ...}` to stdout for command file consumption
- [x] **FIX-C5**: All existing tests pass after rename and bug fixes with updated assertions reflecting fixed behavior

### Auto Doc Script Command

- [x] **SCRIPT-01**: `/mg:auto-doc-script` command file exists with correct frontmatter (name, description, allowed-tools: Bash, Read, Write, Glob, Grep) and implements argument parsing, validation, single-file mode, directory mode, and README generation
- [x] **SCRIPT-02**: `SCRIPT_README.template.md` template exists with `<!-- PURPOSE -->`, `<!-- EXAMPLE -->`, and `<!-- OPTIONAL -->` annotations for all sections (title/description, Prerequisites, Usage, Examples, Options, Output, Notes)
- [x] **SCRIPT-03**: `auto-doc-script` added to COMMANDS array in `auto-doc/install.sh`, deploys correctly with `{TEMPLATES_DIR}` sed resolution
- [x] **SCRIPT-04**: Default output filename is `README.AUTO-DOC.md`, placed in same directory as target file or inside target directory
- [x] **SCRIPT-05**: Directory mode warns at >20 source files, errors on zero source files, handles multiple entry points with summary table and per-script sections
- [x] **SCRIPT-06**: Generated examples use ` ```console ` fenced code blocks with `$` prompt prefix and expected output shown

### Reference Manifest

- [x] **MAN-01**: Per-audience reference manifest files are created in `.mg/docs/reference-manifests/`, each containing symbols and file paths organized by document and section
- [ ] **MAN-02**: Writer agents emit manifest entries after writing each section via `add-manifest-entry.py`, recording every code symbol and file path referenced
- [x] **MAN-03**: Symbols are stored as unqualified identifiers and verified against all LSP `documentSymbol` results at any nesting level without filtering by `SymbolKind`
- [ ] **MAN-04**: Generate orchestrator merges per-audience temp manifests into persisted manifests, replacing matching `(document, section)` keys and preserving non-matching ones
- [ ] **MAN-05**: In initial mode all existing manifests are cleared before generation; in update mode existing manifests are preserved and only regenerated sections are upserted
- [x] **MAN-06**: Stale section cleanup: writer agents emit a `_written_sections` metadata entry; during merge, entries for sections absent from that list are removed
- [ ] **MAN-07**: Verify reads all manifests and checks every `file_paths` entry via filesystem existence and every `symbols` entry via LSP `documentSymbol` on the section's referenced files
- [ ] **MAN-08**: If LSP returns error or empty results for a file, symbol verification is skipped and an info-severity finding is recorded
- [ ] **MAN-09**: Broken references are reported grouped by document and section, distinguishing missing file paths from undefined symbols, all at high severity
- [ ] **MAN-10**: `check-references.py`, its tests, its verify-pipeline invocation, and its artifact inputs to the verifier agent are all deleted
- [ ] **MAN-11**: LSP is the only verification path -- no Grep-based fallback for symbol verification
- [ ] **MAN-12**: Manifest covers audience-specific docs only -- shared docs (OVERVIEW.md, GLOSSARY.md) have no manifest and thus no reference verification

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
| INST-35 | Phase 10 | Complete |
| INST-36 | Phase 10 | Complete |
| INST-37 | Phase 10 | Complete |
| INST-38 | Phase 10 | Complete |
| INST-39 | Phase 10 | Complete |
| INST-40 | Phase 10 | Complete |
| INST-41 | Phase 10 | Complete |
| INST-42 | Phase 10 | Complete |
| INST-43 | Phase 11 | Complete |
| INST-44 | Phase 11 | Complete |
| INST-45 | Phase 11 | Complete |
| INST-46 | Phase 11 | Complete |
| INST-47 | Phase 11 | Complete |
| INST-48 | Phase 11 | Complete |
| INST-49 | Phase 11 | Complete |
| INST-50 | Phase 11 | Complete |
| INST-51 | Phase 11 | Complete |
| INST-52 | Phase 11 | Complete |
| INST-53 | Phase 11 | Complete |
| INST-54 | Phase 11 | Complete |
| INST-55 | Phase 11 | Complete |
| INST-56 | Phase 11 | Complete |
| INST-57 | Phase 11 | Complete |
| SAN-01 | Phase 9 | Complete |
| SAN-02 | Phase 9 | Complete |
| SAN-03 | Phase 9 | Complete |
| SAN-04 | Phase 9 | Complete |
| SAN-05 | Phase 9 | Complete |
| SAN-06 | Phase 9 | Complete |
| SAN-07 | Phase 9 | Complete |
| SAN-08 | Phase 9 | Complete |
| SAN-09 | Phase 9 | Complete |
| SAN-10 | Phase 9 | Complete |
| SAN-11 | Phase 9 | Complete |
| SAN-12 | Phase 9 | Complete |
| SAN-13 | Phase 9 | Complete |
| SAN-14 | Phase 9 | Complete |
| SAN-15 | Phase 9 | Complete |
| SAN-16 | Phase 9 | Complete |
| SAN-17 | Phase 9 | Complete |
| SAN-18 | Phase 9 | Complete |
| SAN-19 | Phase 9 | Complete |
| SAN-20 | Phase 9 | Complete |
| SAN-21 | Phase 9 | Complete |
| SAN-22 | Phase 9 | Complete |
| SAN-23 | Phase 9 | Complete |
| SAN-24 | Phase 9 | Complete |
| REN-01 | Phase 12 | Planned |
| REN-02 | Phase 12 | Planned |
| REN-03 | Phase 12 | Planned |
| REN-04 | Phase 12 | Planned |
| REN-05 | Phase 12 | Planned |
| REN-06 | Phase 12 | Planned |
| REN-07 | Phase 12 | Planned |
| FIX-C1 | Phase 12 | Planned |
| FIX-C2 | Phase 12 | Planned |
| FIX-C3 | Phase 12 | Planned |
| FIX-C4 | Phase 12 | Planned |
| FIX-C5 | Phase 12 | Planned |
| SCRIPT-01 | Phase 13 | Planned |
| SCRIPT-02 | Phase 13 | Planned |
| SCRIPT-03 | Phase 13 | Planned |
| SCRIPT-04 | Phase 13 | Planned |
| SCRIPT-05 | Phase 13 | Planned |
| SCRIPT-06 | Phase 13 | Planned |
| MAN-01 | Phase 14 | Complete |
| MAN-02 | Phase 14 | Pending |
| MAN-03 | Phase 14 | Complete |
| MAN-04 | Phase 14 | Pending |
| MAN-05 | Phase 14 | Pending |
| MAN-06 | Phase 14 | Complete |
| MAN-07 | Phase 14 | Pending |
| MAN-08 | Phase 14 | Pending |
| MAN-09 | Phase 14 | Pending |
| MAN-10 | Phase 14 | Pending |
| MAN-11 | Phase 14 | Pending |
| MAN-12 | Phase 14 | Pending |

**Coverage:**
- v1 requirements: 159 total
- Mapped to phases: 159
- Unmapped: 0

---
*Requirements defined: 2026-03-15*
*Last updated: 2026-03-22 after Phase 14 requirement generation*
