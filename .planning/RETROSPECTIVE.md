# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.1 — milestone

**Shipped:** 2026-05-04
**Phases:** 24 | **Plans:** 64 | **Commits:** 652

### What Was Built

- **`/mg:auto-doc` documentation pipeline** — 5-step pipeline (scan → prepare-templates → generate → auditv2 → fix) producing 13 audience-segmented document types across 4 audiences. Reference manifest with LSP `documentSymbol` verification, recursive section XML, glossary reconciliation, incremental scan mode.
- **`/mg:install` unified installer** — tool.toml-driven discovery, atomic manifest tracking with `fcntl.flock`, two-stage install (install.sh + post-install.md subagent), three install patterns (copy-only, copy+configure, execute-only). Refactored from a 475-line LLM state machine into a 244-line thin orchestrator with all logic in Python subcommands.
- **`/mg:transcript-analyze`** — paginated CLI for navigating Claude Code session exports up to 75MB+, with autonomous investigation slash command. Originally `session-analyzer/`, renamed to `transcript/` during stabilization.
- **Recursive section XML pipeline** — write-section.py with `--parent` flag, nested section trees with depth-first traversal, per-heading reference precision, round-trip fidelity through finalize/assemble/sync.
- **Reference manifest system** — replaced regex-based check-references.py with structured manifest where writers emit exact symbols + paths at generation time, verified deterministically via filesystem and LSP.
- **End-user docs functional-first restructure** — interface detection in scan, 7-section USER_GUIDE template, `<!-- SYNTHESIZED -->` and `<!-- BOUNDARY -->` comment conventions for cross-audience boundaries.
- **Template refiner pipeline** — produces project-specific refined templates with `###`/`####` headings, PURPOSE comments grounded in scan data, generic EXAMPLE blocks. Made the original DOC-04 (`custom_documents` config) mechanism obsolete.

### What Worked

- **Self-contained tool pattern.** Each tool subdirectory (commands/, agents/, scripts/, references/) ships independently. The same install.sh skeleton works across 12+ tools.
- **`tool.toml` metadata.** Single source of truth for tool discovery, preflight requirements, post-install scripts, and detect paths. Made the unified `/mg:install` possible without scanning install.sh.
- **Atomic JSON I/O via `lib/json_io.py`.** `fcntl.flock` + `tempfile.mkstemp` + `os.replace` pattern prevented corruption under concurrent access. Reused everywhere.
- **Refactor to thin orchestrator (Phase 11).** Pulling all deterministic logic out of install.md into Python subcommands (render-status-table, render-tool-picker, render-action-menu, get-install-plan, record-result, render-summary) made the LLM prompt dramatically simpler and tests possible. 475-line prompt → 244 lines.
- **Goal-backward verification.** `/gsd:verify-phase` catching gaps the executor missed kept phase quality high — most phases verified at 100% must-haves on first pass.
- **TDD for Python scripts.** Phases that started with failing tests then implementation (07-01, 11-01, 11-02, 14-01, 16-01, 18-01, 22-01) shipped clean.
- **Auditv2 redesign.** Separating entity extraction from resolution (extract → clear → resolve, with deterministic clearing in the middle) made the audit pipeline both faster and more accurate.
- **Renaming session-analyzer → transcript.** Git rename detection preserved history; broader scope (analyze + export + session-file commands) better fit the directory name.

### What Was Inefficient

- **REQUIREMENTS.md got stale faster than expected.** Phase 6 (FIX-A/B) and Phase 7 (INST-01..12) added requirement IDs to PLAN frontmatter without updating the central traceability table. Phase 8's verification noticed the gap but didn't enforce a fix; the gap propagated through to the milestone audit.
- **ROADMAP.md execution-order line stayed stuck at "1 → 9".** Project was supposed to be 5 phases but expanded to 24; the header line was never updated.
- **Phase 5 and Phase 7 missing VERIFICATION.md.** Both phases were implemented and tested, but the formal verifier was skipped. Phase 5's omission compounded with later stabilization removing most of its work — the requirements table told a story that the codebase didn't.
- **Notes subsystem built then removed.** CMD-05, SCN-06, GEN-03 + supporting scripts (add-note, classify-note) shipped in Phase 1-5, then excised wholesale in commit `90fa640`. ~7 days of work undone.
- **`/mg:auto-doc-script` shipped then removed.** Phase 13 (verified passed) deleted in stabilization. Template `SCRIPT_README.template.md` left orphaned.
- **`/mg:auto-doc` router shipped then removed.** Per user: "didn't really do anything." Could have been caught with one design conversation before Phase 5.
- **Multiple verify pipeline iterations.** Original `auto-doc-verify`, then `auto-doc-verify-mini`, then `auto-doc-verify-singledoc`, then `auto-doc-audit`, finally `auto-doc-auditv2`. Each iteration was cut from the final shape.
- **Update mode separated then merged into generate.** `auto-doc-update.md` shipped as standalone, later folded into `auto-doc-generate.md` (mode: update).

### Patterns Established

- **Self-contained tool pattern with `tool.toml`.** Should be the convention for all future tools.
- **Two-stage install with post-install.md subagent.** For tools that need Claude Code intelligence to configure (settings.json merges, patch application).
- **Three install patterns** (copy-only, copy+configure, execute-only). Covers all current tools; gsd-patches works as execute-only with no install.sh.
- **Markdown LLM prompts + Python deterministic logic.** Strict separation; no embedded Python in .md files.
- **All data flows through files** (`--input` / `--output`), never through shell args. Prevents serialization quirks at command-line boundaries.
- **`{MG_INSTALL_*}` placeholder convention** for sed-replaced paths at install time. Single naming scheme replaced ad-hoc `{SCRIPTS_DIR}` etc.
- **Atomic manifest write pattern.** `fcntl.flock(LOCK_EX)` + `tempfile.mkstemp` + `os.replace`. Concurrent-safe for multi-session installs.
- **Orient-write protocol** for writer agents. Orient once per `##` section to load context, then write each heading. Enabled per-heading reference precision.
- **Reference manifest emission at generation time.** Writers emit exact symbols + paths; verifier checks deterministically via filesystem + LSP. Eliminated false positives from regex-based reference checking.
- **Recursive section XML with slash-separated paths.** Single uniform `<section>` element type at every depth; bare slugs valid for top-level, slash-paths for nested.

### Key Lessons

1. **Update REQUIREMENTS.md traceability when adding REQ-IDs to a phase.** Phase 6 (FIX-A/B) and Phase 7 (INST-01..12) added IDs that never made it into the central table. Future phases must include the traceability update as part of plan creation, not deferred.
2. **Ship the smallest pipeline first; add complexity only when proven.** ~7 days of v1.1 work was the notes subsystem (built → tested → verified → removed) and another ~5 days went to the auto-doc router and the auto-doc-script command. Both were architectural complexity without proven user value. A "would we use this?" gate before Phase 5 / Phase 13 would have saved the work.
3. **Refactor LLM prompts into thin orchestrators ASAP.** Phase 11's refactor (475 lines → 244 lines) made install.md actually testable. Prompts longer than ~250 lines tend to encode hidden state machines that should be Python.
4. **Don't skip VERIFICATION.md "because the implementation works."** Phase 5 and Phase 7 are case studies. Even when tests pass, the formal goal-backward verification catches design gaps the executor and unit tests miss.
5. **Track post-completion drift in REQUIREMENTS.md.** The 15 requirements removed in stabilization stayed `[x]` for ~5 weeks until the milestone audit caught it. A simple convention — when deleting a feature, update its REQ-IDs to `[~] Removed in <commit>` — would prevent this.
6. **Git rename detection is reliable when files move together.** session-analyzer → transcript renamed cleanly because the directory and all files moved in one commit. Splitting renames across commits would have lost history attribution.

### Cost Observations

- Sessions: not tracked (next milestone should add session counting to STATE.md)
- Notable: rolling-TTL session context for permission auto-approval (permission-hooks Phase 8 work) reduced approval prompts substantially during long sessions

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Days | Key Change |
|-----------|--------|-------|------|------------|
| v1.1 | 24 | 64 | 69 | First milestone; established self-contained tool pattern, atomic install, recursive XML, reference manifest, orient-write protocol |

### Cumulative Quality

| Milestone | Tests | Tool Count | Stdlib-Only |
|-----------|-------|------------|-------------|
| v1.1 | 1165+ pytest passing | 12+ installable | install code (mg-install-lib.py) |

### Top Lessons (Verified Across Milestones)

1. (Awaiting v1.2 to cross-validate v1.1 lessons.)
