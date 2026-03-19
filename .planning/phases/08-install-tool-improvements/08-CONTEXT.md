# Phase 8: Install Tool Improvements - Context

**Gathered:** 2026-03-19 (updated with discussion)
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/install-command-v1.1/PLAN.md) + interactive discussion

<domain>
## Phase Boundary

Add two-stage install support to /mg:install: each tool can now have an optional post-install.md that runs as a subagent after install.sh completes. This enables tools that need Claude Code intelligence for configuration (settings.json merges, interactive patch application) to be installed through the unified installer instead of requiring separate commands.

Scope: mg-install-lib.py changes (discovery, adopt, scan-status, checksums), install.md rewrite (per-tool sequential, subagent orchestration), per-tool changes for 5 tools, mechanical [detect] additions for 6 tools, 3 post-install.md content rewrites.

</domain>

<decisions>
## Implementation Decisions

### Two-stage install pattern
- Every tool install follows: install.sh (copy files) then post-install.md (configure, if exists), per-tool sequential
- If either stage fails, stop immediately — do not continue with remaining tools (reverses v1.0 continue-on-error)
- Three install patterns: copy-only (most tools), copy+configure (permission-hooks, cc-regression-test), execute-only (gsd-patches)

### Post-install execution model
- Post-install.md runs as a subagent (Agent tool), not inline
- install.md reads post-install.md from source, spawns a general-purpose Agent with prompt prefix containing target path and source path
- Subagent inherits all parent tools (Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion)
- Post-install.md references paths as provided context in natural language, not as shell variables
- Post-install.md is self-contained with no command frontmatter — written as complete instruction document for a subagent with no prior context
- install.md must include `Agent` in allowed-tools (already added)

### Path definitions
- TARGET_PATH = target project root (e.g., /home/user/projects/road-runner)
- SOURCE_PATH = mg-cc-tools repo root (NOT the individual tool subdirectory)
- Post-install.md files use SOURCE_PATH/<tool-name>/... for tool-specific resources
- These are conceptual names for values passed as plain text in the subagent prompt, not shell variables

### Discovery rule
- discover_tools() requires only tool.toml — no stub install.sh files needed
- Install pattern derived from which files exist alongside tool.toml
- Implementation ordering: discover_tools() must be updated BEFORE any tool's install.sh is removed

### Tool tier changes
- permission-hooks: change to standard = false (requires interactive settings.json config, should not fire during bulk install)
- gsd-patches: change from exclude = true to standard = false (becomes optional, not excluded)
- mg-gsd-wrappers: add standard = false
- cc-regression-test: remains exclude = true — post-install only fires when user explicitly names it

### permission-hooks changes
- Create post-install.md from commands/install-permission-hooks.md (content rewrite, not file move)
- Strip YAML frontmatter, replace $ARGUMENTS with target path from subagent prompt, remove {SOURCE_DIR} placeholder
- install.sh: remove line that copies install-permission-hooks.md to commands/mg/, add stale file cleanup
- Result: /mg:install-permission-hooks no longer appears in target skill list

### gsd-patches changes (execute-only tool)
- gsd-patches runs from mg-cc-tools and modifies GSD workflow files in the target project using structured patch templates with anchor/replace pairs and Claude's intelligence for conflict resolution
- Create post-install.md from commands/apply-gsd-patches.md (content rewrite)
- Remove {PATCHES_DIR}/{SOURCE_PATCHES_DIR} placeholders — reference source directory from subagent prompt prefix
- Remove Step 0 sync check — always reading from source now
- Remove install.sh entirely — nothing to copy anywhere
- Stale file cleanup in post-install.md: remove commands/mg/apply-gsd-patches.md and .claude/gsd-patches/ from target
- No [detect] section — nothing installed to target, not adoptable
- Manifest entry written by install.md calling update-manifest directly after post-install completes
- --source takes the tool subdirectory (e.g., ./gsd-patches), not SOURCE_PATH alone
- Re-apply after GSD updates: user runs /mg:install and selects gsd-patches

### mg-gsd-wrappers changes
- Move snapshot (discuss-methodology.snapshot.md) from commands/mg/ to .claude/mg-gsd-wrappers/references/ in install target
- Show "Requires: gsd-patches" note in install.md status table
- No post-install needed — pure file copy

### cc-regression-test changes
- Create post-install.md (new file): extract inline Python settings.json merge from install.sh
- Rewrite as self-contained subagent instructions for settings.json hook entry merge
- Handle edge cases: settings.json doesn't exist, hooks array doesn't exist, entry already present (idempotent)
- install.sh simplified to just file copies and sed placeholder resolution

### create-context changes
- Move context-template.snapshot from commands/mg/ to .claude/create-context/references/ (.snapshot files in commands/mg/ appear in skill list)

### Mechanical changes (6 tools)
- Add [detect] section to tool.toml for: codebase-health, create-docs, data-provider, debug-triage, new-milestone-gsd, update-backlog
- No other changes needed

### mg-install-lib.py changes
- read_tool_toml(): parse [post_install] and [detect] sections, return post_install_script (string or None) and detect_paths (list)
- discover_tools(): require only tool.toml, derive install pattern from which files exist
- adopt_tools(): check [detect].paths in addition to commands. Detection: (has commands AND all present) OR (has detect paths AND all exist). Both require non-empty set. Execute-only tools skipped.
- scan-status output: include post_install and has_install_sh fields. Corrupt detection: only check command-presence when manifest_entry.commands is non-empty. Execute-only tools write commands: [] in manifest.
- compute_tool_checksums(): add post-install.md as hardcoded root file (like install.sh). Add patches/**/*.md to CHECKSUM_INCLUDE.

### install.md changes
- Step 6: batch to per-tool sequential with three patterns and subagent orchestration
- Step 6 error handling: continue-on-error to stop-on-error
- Step 2b: adopt checks [detect].paths, skips execute-only tools
- Status table: update example for new tiers, show dependency notes
- Key Constraint #5: update excluded tools list (remove gsd-patches)
- Key Constraint #6: add exception for execute-only tools calling update-manifest directly

### Post-install failure detection and UX
- Post-install.md must end with a status marker: `POST-INSTALL: SUCCESS` or `POST-INSTALL: FAILED: <reason>`
- Create TEMPLATE-post-install.md that mandates this marker pattern — the template is the enforcement mechanism
- install.md checks the subagent's returned text for the marker to determine success/failure
- On failure: show 1-line summary ("permission-hooks post-install FAILED: settings.json merge failed") then full subagent output below for debugging context
- No partial retry — user selects the tool again in /mg:install, both stages rerun (install.sh is idempotent)

### No partial state tracking
- If post-install.md fails after install.sh, manifest already has the tool entry (shows "Current")
- User fixes the issue and selects the tool again — install always runs both stages, no skip logic
- No automated rollback

### Stale file cleanup
- permission-hooks: install.sh removes commands/mg/install-permission-hooks.md from target
- gsd-patches: post-install.md removes commands/mg/apply-gsd-patches.md and .claude/gsd-patches/ from target as first step

### Detection paths for adopt
- codebase-health: .claude/codebase-health/scripts/
- create-docs: .claude/create-docs/scripts/
- create-context: .claude/commands/mg/create-context.md
- data-provider: .claude/data-provider/scripts/
- debug-triage: .claude/commands/mg/debug-triage.md
- mg-gsd-wrappers: .claude/commands/mg/discuss-phase.md
- new-milestone-gsd: .claude/commands/mg/new-milestone-gsd.md
- update-backlog: .claude/commands/mg/update-backlog.md
- permission-hooks: .claude/permission-hooks/hooks/
- cc-regression-test: .claude/cc-regression-test/hooks/
- Not adoptable: gsd-patches (execute-only), install (excluded, manifest already exists)

### Claude's Discretion
- Internal code organization within mg-install-lib.py (function structure, helper extraction)
- Test structure and organization for new tests
- Exact error message wording in install.md
- Order of mechanical [detect] additions across 6 tools
- Whether to batch mechanical tool.toml changes or do them one at a time

</decisions>

<specifics>
## Specific Ideas

- Full plan with all decisions resolved: docs/work-queue/todo/install-command-v1.1/PLAN.md
- Current mg-install-lib.py: install/scripts/mg-install-lib.py
- Current install.md: install/commands/install.md
- Current test suite: install/scripts/tests/test_mg_install_lib.py
- permission-hooks source command: permission-hooks/commands/install-permission-hooks.md
- gsd-patches source command: gsd-patches/commands/apply-gsd-patches.md
- gsd-patches patch templates: gsd-patches/patches/*.md

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compute_tool_checksums()`: already handles install.sh as hardcoded root file — post-install.md follows same pattern
- `write_manifest_atomic()`: fcntl.flock + tempfile + os.replace — used by adopt and update-manifest
- `read_tool_toml()`: already parses [tool], [preflight] sections — extend for [post_install], [detect]
- `CHECKSUM_INCLUDE` list: add patches/**/*.md pattern

### Established Patterns
- install.sh scripts follow consistent structure: arg parse, validate source, file copies, sed resolution, manifest update
- All install.sh scripts call update-manifest with --target (project root) --tool (name) --source (tool dir)
- scan-status compact output via --output flag (details to file, summary to stdout)

### Integration Points
- install.md Step 6 is the main orchestration point — changes from batch bash calls to per-tool sequential with Agent tool calls
- adopt_tools() line 757: currently skips tools with no commands — must restructure for detect paths
- scan_status() lines 342-349: command-presence check needs guard for empty commands list

</code_context>

<deferred>
## Deferred Ideas

- v1.0 to v1.1 manifest migration path for existing targets (scan-status may show confusing status during transition — accepted as minor)
- CLAUDE.md update for cross-tool dependency acknowledgment (mg-gsd-wrappers depends on gsd-patches)
- Validation coverage for post-install artifacts (settings.json structural check)
- Updated status table example in install.md (implementer creates from spec)

</deferred>

---

*Phase: 08-install-tool-improvements*
*Context gathered: 2026-03-19 via context import*
