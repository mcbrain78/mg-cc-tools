---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: executing
stopped_at: Phase 16 context supplemented
last_updated: "2026-03-22T21:34:29.650Z"
last_activity: 2026-03-22 -- Plan 15-02 complete (scan pipeline updates with interface detection and exclusion rules)
progress:
  total_phases: 16
  completed_phases: 14
  total_plans: 46
  completed_plans: 45
  percent: 98
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-15)

**Core value:** Automate the creation and maintenance of audience-specific documentation so it stays current as code evolves
**Current focus:** Phase 11 - Add Tooling to Install Command

## Current Position

Phase: 15 of 16 (Auto Doc Enduser Quality)
Plan: 2 of 3 in current phase
Status: In Progress
Last activity: 2026-03-22 -- Plan 15-02 complete (scan pipeline updates with interface detection and exclusion rules)

Progress: [██████████] 98%

## Performance Metrics

**Velocity:**
- Total plans completed: 14
- Average duration: 5min
- Total execution time: 1.08 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-infrastructure | 4/4 | 24min | 6min |
| 02-templates-agent-definitions | 4/4 | 21min | 5min |
| 03-scan-pipeline | 2/2 | 7min | 4min |
| 04-generate-pipeline | 2/2 | 5min | 3min |
| 05-verify-notes-command-router | 2/2 | 8min | 4min |

**Recent Trend:**
- Last 5 plans: 03-02 (4min), 04-01 (3min), 04-02 (2min), 05-01 (3min), 05-02 (5min)
- Trend: Stable

*Updated after each plan completion*
| Phase 02 P01 | 4min | 2 tasks | 6 files |
| Phase 02 P02 | 9min | 3 tasks | 9 files |
| Phase 02 P03 | 3min | 2 tasks | 4 files |
| Phase 02 P04 | 5min | 2 tasks | 3 files |
| Phase 03 P01 | 3min | 2 tasks | 2 files |
| Phase 03 P02 | 4min | 2 tasks | 0 files |
| Phase 04 P01 | 3min | 2 tasks | 1 files |
| Phase 04 P02 | 2min | 2 tasks | 0 files |
| Phase 05 P01 | 3min | 2 tasks | 2 files |
| Phase 05 P02 | 5min | 2 tasks | 4 files |
| Phase 06 P01 | 3min | 2 tasks | 6 files |
| Phase 06 P02 | 3min | 2 tasks | 3 files |
| Phase 06 P03 | 2min | 2 tasks | 3 files |
| Phase 06 P04 | 3min | 1 tasks | 1 files |
| Phase 07 P01 | 30min | 1 tasks | 3 files |
| Phase 07 P02 | 1min | 1 tasks | 13 files |
| Phase 07 P04 | 2min | 2 tasks | 11 files |
| Phase 07 P03 | 4min | 2 tasks | 2 files |
| Phase 08 P01 | 5min | 2 tasks | 2 files |
| Phase 08 P02 | 2min | 2 tasks | 12 files |
| Phase 08 P04 | 2min | 2 tasks | 1 files |
| Phase 08 P03 | 5min | 3 tasks | 6 files |
| Phase 08 P05 | 2min | 1 tasks | 1 files |
| Phase 09 P01 | 5min | 2 tasks | 9 files |
| Phase 09 P02 | 5min | 2 tasks | 4 files |
| Phase 09 P03 | 5min | 2 tasks | 4 files |
| Phase 09 P04 | 5min | 2 tasks | 5 files |
| Phase 10 P01 | 6min | 1 tasks | 2 files |
| Phase 10 P02 | 2min | 2 tasks | 2 files |
| Phase 11 P01 | 4min | 1 tasks | 2 files |
| Phase 11 P02 | 8min | 1 tasks | 2 files |
| Phase 11 P03 | 3min | 2 tasks | 1 files |
| Phase 12 P01 | 13min | 2 tasks | 60 files |
| Phase 12 P02 | 3min | 2 tasks | 7 files |
| Phase 13 P01 | 3min | 3 tasks | 3 files |
| Phase 14 P01 | 3min | 2 tasks | 3 files |
| Phase 14 P02 | 2min | 2 tasks | 5 files |
| Phase 14 P03 | 4min | 2 tasks | 4 files |
| Phase 15 P01 | 5min | 2 tasks | 4 files |
| Phase 15 P03 | 2min | 1 tasks | 1 files |
| Phase 15 P02 | 3min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 5-phase structure derived from requirement dependencies: infrastructure first, then templates/agents, then pipeline steps sequentially (scan, generate, verify), with commands integrated into their respective pipeline phases
- [01-01]: Followed codebase-health atomic JSON I/O pattern exactly (os.replace via temp file)
- [01-01]: Used structured markdown for schema (LLM-readable, no validator dependency)
- [01-01]: Style guide organized as universal + per-audience + Diataxis + section + formatting (~200 lines)
- [01-01]: Command stubs include YAML frontmatter with name, description, allowed-tools
- [01-02]: Confidence uses top_score/total_score formula to penalize multi-audience ambiguity below 0.5
- [01-02]: merge-scan.py processes all *.json in scan-dir (no scan- prefix filter) for flexibility
- [01-02]: Gap analysis merges as sorted union for deterministic output
- [01-03]: Hyphenated filenames matching codebase-health convention; importlib.machinery.SourceFileLoader for test imports
- [01-03]: Best-effort regex symbol detection (no AST) — sufficient for this use case without additional dependencies
- [01-03]: staleness-check uses lib/git_helpers for all git log operations, only direct subprocess for is-git-repo check
- [01-04]: Mirrored codebase-health/install.sh structure exactly for consistency across mg-cc-tools
- [01-04]: Scaffolding checks .mg/docs/ existence to preserve user customizations on re-install
- [01-04]: Agent directory created empty (Phase 2 fills); sed resolution handles future agent files
- [02-01]: TEMPLATE.md adapted from codebase-health scanner pattern to writer pattern: same structure but oriented toward document generation
- [02-01]: Template exemplars use portfolio analytics platform (Road Runner) as realistic domain example throughout
- [02-01]: Glossary agent uses {TEMPLATES_DIR} and references/style-guide.md placeholders for install-time sed resolution
- [Phase 02]: TEMPLATE.md adapted from codebase-health scanner pattern to writer pattern: same structure but oriented toward document generation
- [Phase 02]: Template exemplars use portfolio analytics platform (Road Runner) as realistic domain example throughout
- [02-02]: Consistent DataForge example project across all developer and agent templates for coherent cross-template references
- [02-02]: Agent templates use explicit MUST/SHOULD/MUST NOT constraint language per Codified Context paper
- [02-02]: DevOps OPERATIONS template mirrors 02-RESEARCH.md detailed example as primary reference
- [02-03]: Each agent includes audience-specific post-processing steps in Process (jargon check, code review, heading uniqueness, rollback verification)
- [02-03]: Agent definitions kept lean (80-100 lines) by referencing style guide and templates by path rather than inlining
- [02-03]: Convention sections use exact language from CONTEXT.md locked decisions for traceability
- [Phase 02-04]: Staleness scanner uses conservative classification: only marks stale/broken with concrete evidence from git or dead references
- [Phase 02-04]: Verifier agent uses 5-tier severity model (critical/high/medium/low/info) matching docs-verify-report.md format
- [Phase 02-04]: install.sh uses cp -r preserving subdirectory structure for templates
- [03-01]: Single generic scan-audience.md template rather than 4 audience-specific agents -- specialization comes from documents list and templates
- [03-01]: Orientation writes TWO files: scan-orientation.md (human-readable) and scan-project.json (structured data for merge) to address Pitfall 3
- [03-01]: Expansion outlines generated by orchestrator LLM inline, not by classify-note.py script (per SCN-06 requirement)
- [03-01]: GSD context loading guarded by both directory existence AND config flag (Pitfall 5)
- [03-01]: Staleness scripts invoked with --docs-dir (directory-level) not --doc-file (Pitfall 1)
- [03-02]: install.sh required no modification -- existing agents/*.md wildcard and sed resolution loop handled scan-audience.md automatically
- [03-02]: Road-runner validation confirmed as effective quality gate: scan detected 14 technologies, 27 components, 6 entry points, 70 source material entries
- [Phase 04-01]: OVERVIEW.md generated inline by orchestrator (not via subagent) since orchestrator already has generation context
- [Phase 04-01]: Update mode approval uses AskUserQuestion with 4 options: approve all, by document, by severity, cancel
- [Phase 04-01]: Notes presented as separate approval group after staleness sections
- [Phase 04-01]: Section identifiers normalized to slug format to bridge template Title Case and index hyphenated-lowercase
- [Phase 04-01]: Notes inbox updated as single atomic write to prevent partial-update corruption
- [Phase 04-02]: Road-runner validation confirmed as effective quality gate for generate pipeline (mirrors 03-02 pattern)
- [Phase 04-02]: No code changes needed for validation -- install.sh already handles generate command via existing COMMANDS array and sed resolution loop
- [Phase 05-01]: Verify command uses single verifier agent (not parallel by category) since 6 sequential checks are simpler than per-finding parallelization
- [Phase 05-01]: LSP symbol verification override delivered via Task prompt, not by modifying verifier.md agent definition
- [Phase 05-01]: AskUserQuestion added to add-docs allowed-tools for classification correction UX per research recommendation
- [Phase 05-02]: Router follows codebase-health.md pattern precisely: state detection + routing, never runs pipeline steps itself
- [Phase 05-02]: check-references.py index-based lookup replaces O(symbols x files) per-symbol os.walk to prevent timeouts on real projects
- [Phase 05-02]: --skip-symbol-check flag delegates symbol verification to LSP via verifier agent (faster and more accurate)
- [Phase 05-02]: Verify-generate feedback loop deferred as future work item (not in v1 scope)
- [Phase 06-01]: File-based I/O pattern (--input/--output files) replaces CLI args for structured data to avoid shell metacharacter escaping
- [Phase 06-01]: Rank-based severity filtering: --severity high returns high AND critical via index comparison on SEVERITY_ORDER
- [Phase 06-01]: Rejected input saved to .rejected file for debugging without corrupting pipeline
- [Phase 06-02]: Used {SCRIPTS_DIR} placeholders in agent definitions for consistency with existing install.sh sed resolution pattern
- [Phase 06-02]: Baked LSP symbol verification into Check 1 and glossary reconciliation into Check 2 to eliminate all Task prompt overrides
- [Phase 06-02]: Verify findings schema uses flat array with 7 required fields -- aggregation into systemic patterns happens at presentation layer
- [Phase 06]: Verify command simplified to pure parameter passing -- all verification behavior baked into verifier.md agent definition
- [Phase 06]: Router reads docs-verify-findings.json directly (no list-verify-findings.py dependency) per CONTEXT.md decision
- [Phase 06]: [Phase 06-04]: 3-tier approval flow: staleness -> verify findings -> notes, with merged drill-in and findings lifecycle (generate reads, never clears)
- [Phase 07]: Set requires-python to >=3.11 (tomllib floor) rather than >=3.13 per Pitfall 4 analysis
- [Phase 07]: Omit exclude field for non-excluded tools (false is the default); omit optional key when array would be empty
- [Phase 07-01]: Used commands/* (all files) in checksum scope to match install.sh behavior, ensuring non-.md files trigger Modified status
- [Phase 07-01]: Corrupt status check runs before version/checksum comparison since missing commands is more severe than version drift
- [Phase 07-01]: WORKSPACE_DIRS maps tool names to expected scaffold directories for validate subcommand
- [Phase 07]: Manifest update block uses TOOL_SOURCE_DIR (resolved from dirname $0) to avoid collision with existing SCRIPT_DIR in install.sh scripts
- [Phase 07]: Script path uses relative ./install/scripts/mg-install-lib.py since command always runs from mg-cc-tools directory -- no sed resolution needed
- [Phase 07]: AskUserQuestion used ONLY for target selection; action selection uses numbered text prompts parsed by the LLM
- [Phase 07]: Bootstrap install.sh does NOT call update-manifest per Pitfall 7 -- mg-cc-tools is the source repo, not a target
- [Phase 08]: Used loop over hardcoded root files for compute_tool_checksums instead of separate checks
- [Phase 08]: discover_tools() requires only tool.toml -- no stub install.sh files needed for execute-only tools
- [Phase 08-02]: gsd-patches changed from exclude=true to standard=false (not adoptable, no [detect])
- [Phase 08-02]: Template uses natural language path references, no shell variable placeholders
- [Phase 08]: gsd-patches install.sh deleted; execute-only tool uses post-install.md for all work from source
- [Phase 08]: permission-hooks post-install.md preserves all 5 steps from original command, adapted to subagent prompt prefix path references
- [Phase 08]: cc-regression-test post-install.md consolidates settings.json merge into single inline Python script with edge case handling
- [Phase 08]: Snapshot files relocated to .claude/<tool-name>/references/ to prevent skill list pollution
- [Phase 08]: Step 6 uses per-tool sequential with stop-on-error and three install patterns (copy-only, copy+configure, execute-only)
- [Phase 09]: createdAt handled as epoch-ms based on actual sample data; conftest uses sys.path.insert for importability; error detection independent of compactor (SAN-22)
- [Phase 09]: Detailed error detection via _detect_errors_detailed() separate from overview detect_errors() to preserve full text and type classification
- [Phase 09]: Flow classification purely mechanical using role + content block type -- no AI classification per CONTEXT.md D2
- [Phase 09]: resolve_agent_prefix exits with error listing matches for ambiguous prefixes, clean message for zero matches
- [Phase 09]: Agent deep dive is summary mode (tool name + input summary + status), msg is content mode (full text + persisted recovery)
- [Phase 09]: Search recovers persisted outputs lazily before regex matching per CONTEXT.md strategy
- [Phase 09]: Export reloads full JSON (compactor needs chunks for its own drop logic)
- [Phase 09]: install.sh follows data-provider pattern (simpler than codebase-health, no agents/references)
- [Phase 10]: _get_ordered_tools() is single source of truth for tool numbering shared by picker and resolver
- [Phase 10]: render_status_table uses its own three-tier filtering (needs excluded tier) not _get_ordered_tools
- [Phase 10]: Unicode separators match existing install.md visual style; dynamic column widths from data
- [Phase 10]: Step 2 uses single render-status-table call with verbatim display directive (replacing ~50 lines of template)
- [Phase 10]: Scenario A/B/C menus remain LLM-rendered; only tool picker and resolver sub-flows use Python subcommands (INST-41)
- [Phase 11]: _determine_scenario is shared by render_action_menu and resolve_action via direct call -- single source of truth prevents scenario drift
- [Phase 11]: Scenario B triggers on corrupt and adopted statuses in addition to update and modified (INST-51 behavior change)
- [Phase 11]: _resolve_menu_option helper encapsulates per-scenario option-to-action mapping as a dict lookup
- [Phase 11]: auto-adopt runs adopt_tools before scan_status when flag set and no manifest, then re-runs scan to get updated statuses
- [Phase 11]: render_summary classifies actions into installed/updated/failed counts using substring matching
- [Phase 11]: record-result uses argparse mutually_exclusive_group for --success/--failed CLI enforcement
- [Phase 11]: get-install-plan compact stdout returns tool+pattern+post_install (enough for install loop)
- [Phase 11]: Single consolidated display rule replaces per-subcommand echo instructions in install.md
- [Phase 12]: Bulk sed s/create-docs/auto-doc/g followed by explicit s/add-docs/auto-doc-add/g -- independent patterns
- [Phase 12]: install.sh migration path: detect old create-docs installation, remove stale files, clean manifest with inline python3, then deploy auto-doc
- [Phase 12]: staleness-check.py internal check_staleness() returns bare list, CLI wraps in dict -- dual-output pattern preserves both API usability and merge compatibility
- [Phase 12]: note_id wins over id per schema contract -- breaking change accepted since add-to-generate round-trip never completed
- [Phase 12]: check-references.py removed from scan pipeline but kept for verify pipeline (Phase 14 will retire it)
- [Phase 13]: Template placed at top-level templates/ (not in audience subdirectory) since script READMEs are audience-agnostic
- [Phase 13]: convert.py CSV-to-JSON converter used as exemplar domain throughout template (realistic standalone script)
- [Phase 13]: Lightweight single-agent command pattern (no Task/AskUserQuestion) for fully autonomous script README generation
- [Phase 14]: Followed add-verify-finding.py pattern for manifest upsert script; _written_sections metadata bypass accepts empty symbols/file_paths with sections_written list
- [Phase 14]: Manifest emission inserted after docs-meta comment in per-section loop -- extends existing per-section pattern
- [Phase 14]: Generate orchestrator performs manifest merge inline between Stage 2 and Stage 3 with stale section cleanup via _written_sections metadata
- [Phase 14]: Verifier reads structured manifests from .mg/docs/reference-manifests/ instead of regex-extracted reference files
- [Phase 14]: No Grep fallback for symbol verification -- LSP errors produce info-severity findings and skip
- [Phase 15]: user_interfaces optional on project_model -- absent field means CLI-style fallback (backward compatible)
- [Phase 15]: SYNTHESIZED comment pattern: scan writes index with source_files: [] and synthesized_from: [field list], writer generates from project model
- [Phase 15]: BOUNDARY comment pattern: negative guidance for scan (skip indexing) and writer (cross-reference alternate document)
- [Phase 15]: All 7 USER_GUIDE exemplars use road-runner domain with web-UI style; WRITER NOTE guides CLI/API adaptation
- [Phase 15]: Writer determines interface_style from project_model.user_interfaces at runtime, defaulting to CLI when absent (backward compatible)
- [Phase 15]: Interface detection uses 3-priority chain: config-first, heuristic+AskUserQuestion confirmation, non-interactive fallback

### Pending Todos

1. Fix shell metacharacter escaping in add-finding CLI args (area: codebase-health) — `.planning/todos/pending/2026-03-17-fix-shell-metacharacter-escaping-in-add-finding-cli-args.md`
2. Add session directory cleanup command (area: tooling) — `.planning/todos/pending/2026-03-19-add-session-directory-cleanup-command.md`
3. Create rich prompt renderer as AskUserQuestion alternative (area: tooling) — `.planning/todos/pending/2026-03-21-create-rich-prompt-renderer-as-askuserquestion-alternative.md`
4. Create mg:add-todo command that preserves verbatim user input (area: tooling) — `.planning/todos/pending/2026-03-21-create-mg-add-todo-command-that-preserves-verbatim-user-input.md`
5. Add auto-loop mode to auto-improve command (area: tooling) — `.planning/todos/pending/2026-03-21-add-auto-loop-mode-to-auto-improve-command.md`
6. Create mg command to arrange planning files into GSD plans (area: tooling) — `.planning/todos/pending/2026-03-22-create-mg-command-to-arrange-planning-files-into-gsd-plans.md`
7. Create mg:add-phase-with-context compound command (area: tooling) — `.planning/todos/pending/2026-03-22-create-mg-add-phase-with-context-compound-command.md`
8. Create mg:formalize-plan command for structured plan generation (area: tooling) — `.planning/todos/pending/2026-03-22-create-mg-formalize-plan-command-for-structured-plan-generation.md`
9. Add pyright strict mode compliance (area: tooling) — `.planning/todos/pending/2026-03-22-add-pyright-strict-mode-compliance.md`

### Roadmap Evolution

- Phase 6 added: Fix verify feedback loop and scan output
- Phase 7 added: install command
- Phase 8 added: install tool improvements
- Phase 9 added: session analyzer
- Phase 10 added: create a renderer for the install command
- Phase 11 added: add tooling to install command
- Phase 12 added: auto doc rename and cleanup
- Phase 13 added: auto doc script
- Phase 14 added: auto doc reference manifest
- Phase 15 added: auto doc enduser quality
- Phase 16 added: auto doc incremental scan

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-03-22T21:34:29.647Z
Stopped at: Phase 16 context supplemented
Resume file: .planning/phases/16-auto-doc-incremental-scan/16-CONTEXT.md
