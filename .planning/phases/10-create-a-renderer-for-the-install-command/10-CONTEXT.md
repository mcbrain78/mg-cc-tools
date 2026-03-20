# Phase 10: Create a Renderer for the Install Command - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/todo/install-command-v1.2/CONCEPT.md)

<domain>
## Phase Boundary

Move the install command's status table rendering (Step 2) and tool picker rendering (Step 3) from LLM-generated output to deterministic Python subcommands in `mg-install-lib.py`. The install flow logic itself does not change — only the rendering and input parsing layers are replaced.

</domain>

<decisions>
## Implementation Decisions

### render-status-table subcommand
- Input: full scan-status JSON (the `--output` file, not the compact stdout summary — compact summary lacks `installed_version` and `current_version` fields)
- Output: formatted status table to stdout, ready for verbatim display
- Groups tools into three tiers: standard, optional (marked `*`), excluded — with section headers and separators
- Computes summary line with correct counts scoped to non-excluded tools only
- Includes status legend at bottom
- Shows version transition annotations for update status (e.g., "Update (0.2.0 -> 0.3.0)")
- Column alignment is deterministic (computed from actual data widths)

### render-tool-picker subcommand
- Input: full scan-status JSON (same `--output` file)
- Output: numbered tool list to stdout with section headers
- Shows all non-excluded tools regardless of status — covers both fresh install and reinstall/update scenarios
- Tools with non-available status get annotations: (Corrupt), (Modified), (Current), etc.
- Numbered sequentially across standard and optional sections (standard first)
- Filters out excluded tools

### resolve-tool-selection subcommand
- Input: scan-status JSON + user's text response
- Output: JSON list of resolved tool names
- Parses numbers ("2,9"), ranges ("1-3"), names ("permission-hooks"), mixed ("1-3, permission-hooks"), and "all"
- Returns error JSON for invalid input (unknown number, unrecognized name)

### Ordering contract
- `render-tool-picker` and `resolve-tool-selection` must use an identical tool ordering function
- Both derive the ordered list from the scan-status JSON tool array, filtered to non-excluded, grouped standard-first then optional
- This shared logic must be a single internal function, not duplicated across subcommands

### Prompt changes to install.md
- Step 2: remove ~60 lines of table template, legend, and formatting rules (lines 82-131); replace with a `render-status-table` call and "display verbatim" directive
- Step 3: add `render-tool-picker` + `resolve-tool-selection` calls for the "Select specific tools" sub-flow
- Tool picker invoked in Scenario A option [2]; for Scenarios B and C, invoked when user types tool names or numbers instead of a menu option
- Scenario A/B/C top-level menus remain LLM-rendered (short, static, reliable)

### Files changed
- `install/scripts/mg-install-lib.py` — 3 new subcommands + argparse wiring
- `install/scripts/tests/test_mg_install_lib.py` — tests for each subcommand
- `install/commands/install.md` — simplify Steps 2 and 3
- `.claude/commands/mg/install.md` — deployed copy (keep in sync)

### Claude's Discretion
- Column width calculation algorithm (fixed padding vs dynamic)
- Unicode box-drawing characters vs ASCII for separators
- Whether `render-status-table` also accepts the mg-cc-tools version string as argument (for the header line) or reads it from the JSON
- Internal helper function naming and organization within mg-install-lib.py
- Test fixture design (inline JSON vs file-based)
- argparse subcommand naming convention (`render-status-table` vs `render_status_table`)

</decisions>

<specifics>
## Specific Ideas

- The status table output should match the existing visual style established in install.md's template (Unicode line separators, `*` for optional tools, `✓` for current status)
- Tool picker example from CONCEPT.md shows the target format with section headers and right-aligned numbers
- Root cause is specifically that LLMs fail to reproduce exact templates faithfully — not that the templates are ambiguous

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mg-install-lib.py` already has `scan_status()` which produces the full JSON these renderers consume
- `discover_tools()` and `get_tool_commands()` provide the tool ordering logic that the shared ordering function should mirror
- Existing argparse wiring pattern in `mg-install-lib.py` for adding subcommands (`cmd_scan_status`, `cmd_update_manifest`, etc.)

### Established Patterns
- Subcommands use `--output` for file-based output, stdout for inline; new renderers always output to stdout
- `scan_status()` returns tools in `discover_tools()` order — the shared ordering function should use this same order as its base

### Integration Points
- `install.md` Step 2 calls `scan-status --output /tmp/mg-scan-status.json` — the renderers read this same file
- `install.md` Step 3 scenario routing stays in the LLM — renderers are called after the user selects a numbered option
- `.claude/commands/mg/install.md` must be kept in sync with source after prompt changes

</code_context>

<deferred>
## Deferred Ideas

- Action menu rendering (Step 3 scenario A/B/C menus) — short, static, LLM handles reliably
- Summary rendering (Step 8) — low variance, not worth the complexity
- Any changes to the install flow logic itself

</deferred>

---

*Phase: 10-create-a-renderer-for-the-install-command*
*Context gathered: 2026-03-20 via context import*
