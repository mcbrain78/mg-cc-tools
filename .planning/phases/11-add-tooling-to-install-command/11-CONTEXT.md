# Phase 11: Add Tooling to Install Command - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning
**Source:** Merged — original import + discussion (docs/work-queue/todo/install-command-v1.3/CONCEPT.md)

<domain>
## Phase Boundary

Refactor the install command from a 475-line LLM-driven state machine into a thin orchestrator where all deterministic logic (scenario selection, action mapping, install planning, result tracking, summary rendering) lives in Python subcommands. The LLM's only jobs become: echo output, collect input, spawn agents. This is a reliability refactor with one deliberate behavior change (Scenario B expanded to include corrupt/adopted statuses).

</domain>

<decisions>
## Implementation Decisions

### Auto-adopt via `--auto-adopt` flag on scan-status
- Add `--auto-adopt` flag to the existing `scan-status` subcommand
- When flag is set and `manifest_exists` is false, scan-status checks for existing installations (command files + detect paths) and runs `adopt_tools()` before computing statuses
- Output includes `"auto_adopted": ["tool1", "tool2"]` when adoption occurred
- Without the flag, scan-status remains a pure read operation — no side effects
- Replaces Step 2b entirely — the LLM never checks `manifest_exists` or decides whether to adopt

### `render-action-menu` subcommand
- Input: `--input <scan-status-json>`
- Output: correct scenario menu as plain text to stdout
- Uses shared `_determine_scenario(scan_data)` helper for scenario derivation
- Scenario A: `installed_total == 0` — nothing installed
- Scenario B: `update > 0 or modified > 0 or corrupt > 0 or adopted > 0` — some need attention (behavior change from v1.2: now triggers on corrupt/adopted)
- Scenario C: `installed_total > 0` and none of B's conditions — all current
- Computes dynamic counts for menu labels: "N tools needing attention", "N remaining standard", "N tools" for bulk install
- Replaces Step 3's three scenario templates and the LLM's scenario selection logic

### `resolve-action` subcommand
- Input: `--input <scan-status-json> --selection "<user_response>"`
- Output: JSON with `action` and `tools` fields (or `error`)
- Uses the same shared `_determine_scenario(scan_data)` helper as render-action-menu
- Maps user's menu selection to correct action with pre-computed tool list per scenario
- Scenario A: [1] install all standard, [2] select specific, [3] edit standard list
- Scenario B: [1] fix/update N tools, [2] fix/update + install missing, [3] install missing only, [4] edit standard list, [5] check capabilities
- Scenario C: [1] install remaining standard, [2] reinstall all, [3] edit standard list, [4] check capabilities
- For tool names/numbers (not a menu option), delegates to `resolve_tool_selection()` internally
- Replaces Step 3's option-to-action mapping across three scenarios

### `get-install-plan` subcommand
- Input: `--input <scan-status-json> --tools <comma-separated-list>`
- Reads `target` path from the scan-status JSON — no `--target` argument needed
- Output: JSON array of install instructions with `tool`, `pattern`, `expected_action`, `install_cmd`, `post_install`, `commands` fields
- Determines install pattern from `has_install_sh` and `post_install` fields: `copy_only` = has_install_sh && !post_install, `copy_configure` = has_install_sh && post_install, `execute_only` = !has_install_sh && post_install
- Pre-computes `expected_action` from tool's current status and pattern (available→installed, update/modified/corrupt/adopted→updated, current→reinstalled) with " (configured)" suffix for copy_configure and execute_only
- Includes `commands` list from scan-status per tool so LLM never provides command filenames
- Uses `--output` for file output (consistent with scan-status and validate)

### `render-preflight` subcommand
- Input: `--input <preflight-json>` (output file from existing `preflight` subcommand)
- Output: formatted preflight results to stdout (human-readable, no JSON mixed in)
- Prerequisite: existing `preflight` subcommand gains `--output` support (same pattern as scan-status and validate)
- Prompt calls preflight with `--output /tmp/mg-preflight.json`, checks `all_passed` from compact stdout JSON, then calls render-preflight for display
- The preflight JSON file is also consumed by render-summary for capability data

### `record-result` subcommand
- Input: `--file <path> --tool <name> --success|--failed --plan <install-plan-json>`
- Append-only helper for building install results file during Step 6
- Reads install plan JSON to look up tool's `commands` list and `expected_action`
- On `--success`: writes `{"tool": "...", "action": "<expected_action>", "commands": [...]}`
- On `--failed`: writes `{"tool": "...", "action": "failed", "commands": []}`
- Creates file with `[]` if it doesn't exist; each call reads, appends, rewrites (sequential, no locking needed)

### `render-summary` subcommand
- Input: `--results <install-results-json> --input <scan-status-json> --preflight <preflight-json>`
- Output: formatted summary table to stdout
- Reads results file, formats summary with action column, command filenames, counts
- Merges capability data from preflight JSON (LSP status, missing optional tools) if `--preflight` provided
- Replaces Step 8's LLM-reconstructed summary from memory

### Shared scenario logic (design constraint)
- `render-action-menu` and `resolve-action` MUST use a single shared `_determine_scenario(scan_data)` function
- Duplicating this logic is the exact class of bug this refactor eliminates — if one is updated and the other is not, option numbers would mean different things in the menu vs. the resolver

### Prompt consolidation
- Replace per-subcommand "IMPORTANT: echo verbatim" instructions with a single rendering rule at the top of the prompt
- Rendering rule: `render-*` subcommands produce user-facing content that must be echoed verbatim as fenced code blocks; other subcommands output machine-readable JSON that must NOT be echoed
- Consolidated directive covers render-status-table, render-action-menu, render-preflight, render-validation, render-summary

### CLI argument convention
- All subcommands that read scan-status use `--input <path>` (consistent with render-status-table and render-tool-picker)
- render-summary uses `--input` for scan-status, `--results` for install results, `--preflight` for preflight file

### What stays in the prompt (LLM territory)
- Step 1: target selection via AskUserQuestion (user interaction)
- Step 3: Edit Standard Install List sub-flow (interactive toggle loop, ~37 lines)
- Step 5: Capability check display (simple one-field conditional, rarely shown)
- Step 6: Agent spawning for post-install.md (genuinely needs LLM + Agent tool)
- Step 6: POST-INSTALL marker parsing (LLM reads Agent output)
- Step 6: Stop-on-error decision (LLM must halt the loop)
- Free text fallback: when resolve-action returns an error, LLM can try to interpret

### What gets deleted from the prompt
- Three scenario menu templates (A/B/C) → render-action-menu
- Option-to-action mapping tables → resolve-action
- Step 2b adoption check (entire section) → auto-adopt in scan-status
- Per-tool pattern determination (if/elif on fields) → get-install-plan
- Preflight result formatting → render-preflight
- Summary table construction from memory → render-summary + record-result
- Validation result formatting → render-validation
- Per-subcommand echo instructions (2x) → single display rule
- Hardcoded /tmp/mg-*.json paths → per-target subdirectories

### `render-validation` subcommand
- Input: `--input <validate-json>` (output file from existing `validate` subcommand)
- Output: formatted validation results to stdout (human-readable PASS/WARNING lines + count)
- Follows the same pattern as render-preflight: validate writes to file via `--output`, render-validation reads it
- Replaces Step 7's LLM-formatted validation output
- Covered by the consolidated rendering rule (render-* subcommands produce user-facing content)

### Per-target temp file directories
- Inter-step files use per-target subdirectories: `/tmp/mg-install-<target-basename>/`
- Example: installing to road-runner uses `/tmp/mg-install-road-runner/scan-status.json`, `preflight.json`, `install-plan.json`, `install-results.json`, `validate.json`
- Python auto-creates the directory when writing the first `--output` file (scan-status)
- Prevents collision when running two install sessions to different target projects simultaneously
- Target basename derived from the target path (e.g., `/home/user/projects/road-runner` → `road-runner`)

### Stdlib-only constraint
- All new code stays stdlib-only, consistent with the existing library (no pip dependencies)

### Claude's Discretion
- Internal function organization within mg-install-lib.py (helper placement, private function naming)
- Test structure and fixture design for new subcommands
- Exact formatting of render-preflight output (PASS/FAIL markers, grouping style)
- Exact formatting of render-validation output (PASS/WARNING layout, issue details)
- Exact formatting of render-summary output (column widths, separators, capability section layout)
- How to structure the install.md rewrite (section ordering, comment placement)
- Argparse wiring details for new subcommands

</decisions>

<specifics>
## Specific Ideas

- The orchestration loop for each step becomes: `run Python → echo output → [get user input → run Python] → next step`
- install.md prompt target: under 250 lines (from ~475)
- Zero conditional rendering in the prompt (no "if scenario A... elif scenario B...")
- Scenario B menu labels use dynamic counts: "N tools needing attention", "N remaining standard"
- expected_action values: "installed", "updated", "reinstalled" with optional " (configured)" suffix
- record-result: LLM only passes `--tool` and `--success`/`--failed` — no action or command filenames

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mg-install-lib.py`: Existing subcommands (scan-status, preflight, validate, render-status-table, render-tool-picker, resolve-tool-selection) provide the pattern for new subcommands
- `_determine_scenario()`: New shared function, but follows the existing `resolve_tool_selection()` pattern of shared helpers
- `--output` pattern: Already used by scan-status and validate subcommands

### Established Patterns
- File-based I/O: `--input`/`--output` for structured data (established in Phase 6)
- Render subcommands: render-status-table and render-tool-picker established the "Python renders, LLM echoes" pattern (Phase 10)
- Atomic JSON I/O: os.replace via temp file (established in Phase 1)

### Integration Points
- `scan-status` subcommand: gains `--auto-adopt` flag
- `preflight` subcommand: gains `--output` support
- `install.md` command prompt: complete rewrite to thin orchestrator
- `.claude/commands/mg/install.md`: deployed copy must stay in sync

</code_context>

<deferred>
## Deferred Ideas

- Edit Standard Install List extraction to Python — stays in prompt for now (~37 lines, low usage)
- Changes to install.sh scripts — not in scope
- Changes to tool.toml format — not in scope
- Verify-generate feedback loop — separate work item

</deferred>

---

*Phase: 11-add-tooling-to-install-command*
*Context gathered: 2026-03-20 via context import*
