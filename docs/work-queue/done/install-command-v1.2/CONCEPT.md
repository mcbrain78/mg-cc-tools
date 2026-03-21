# Install Command v1.2 — Deterministic Rendering

## Problem Statement

The install command's UI rendering is delegated to the LLM, producing non-deterministic output across runs:

1. **Status table (Step 2)** — LLM computes summary counts inline, leading to off-by-one errors (e.g., "Available: 9" when 10 tools are available). Column alignment and section grouping varies.

2. **Tool picker (Step 3, option [2])** — When the user selects "Select specific tools", the LLM freestyles the sub-menu. Sometimes it shows numbered options (allowing selection by number), sometimes it shows an unnumbered list (forcing the user to type tool names). Headers for standard/optional sections appear inconsistently.

3. **Selection parsing** — The LLM parses user input ("2,9", "1-3", "permission-hooks") without defined rules, leading to inconsistent interpretation.

These are all deterministic rendering/parsing tasks that don't require LLM intelligence.

## Root Cause

`install.md` contains exact formatting templates (a 28-line ASCII table example, a 7-line legend block, and 8 formatting rules). The LLM fails to faithfully reproduce them — miscounting summary values, misaligning columns, and varying layout between runs. The problem is not ambiguity in the instructions but that LLMs are unreliable at deterministic rendering tasks even from concrete templates.

## Solution

Move rendering and input parsing to Python subcommands in `mg-install-lib.py`. The install command prompt calls these and displays output verbatim, keeping the LLM focused on orchestration and decisions.

### New subcommands

#### `render-status-table`

Input: full scan-status JSON (the `--output` file, not the compact stdout summary — the compact summary lacks `installed_version` and `current_version` fields needed for version transition display)
Output: formatted status table to stdout (ready to display verbatim)

Handles:
- Standard / optional / excluded grouping with section headers
- Column alignment
- Summary line with correct counts (non-excluded only)
- Status legend
- Version transition annotations (e.g., "Update (0.2.0 -> 0.3.0)")

#### `render-tool-picker`

Input: full scan-status JSON (same `--output` file as `render-status-table`)
Output: numbered tool list to stdout

Shows all non-excluded tools regardless of status. This covers both fresh installs (Scenario A) and reinstall/update scenarios (B/C) where the user types a tool name at the main prompt. Tools with non-available status get annotations (Corrupt, Modified, Current, etc.) so the user can make informed choices.

```
Select tools to install:

  Standard
  ────────────────────────────────────────────────────────
   1. codebase-health      Scan, verify, and fix code health issues
   2. create-context       Create context snapshots for LLM prompts
   ...

  Optional
  ────────────────────────────────────────────────────────
   8. data-provider        Research and map external data field sources
   9. gsd-patches          Apply GSD methodology patches
  10. mg-gsd-wrappers      GSD workflow wrappers (plan, execute, discuss)
  11. permission-hooks     Claude Code permission guard hooks (Corrupt)

Type numbers, names, or 'all':
```

Handles:
- Numbered sequentially across sections
- Status annotation for non-available tools (Corrupt, Modified, etc.)
- Filters out excluded tools
- Consistent column alignment

#### `resolve-tool-selection`

Input: scan-status JSON + user's text response
Output: JSON list of resolved tool names

Parses:
- Numbers: "2,9" -> ["create-context", "gsd-patches"]
- Ranges: "1-3" -> ["codebase-health", "create-context", "create-docs"]
- Names: "permission-hooks" -> ["permission-hooks"]
- Mixed: "1-3, permission-hooks" -> [...]
- "all" -> all non-excluded tools

Returns error JSON if invalid input (unknown number, unrecognized name).

**Ordering contract:** `render-tool-picker` and `resolve-tool-selection` must use an identical tool ordering function to assign and resolve numbers. Both subcommands derive the ordered list from the scan-status JSON tool array (filtered to non-excluded, grouped standard-first then optional). This shared logic should be a single internal function, not duplicated.

### Prompt changes

Simplify `install.md` Steps 2 and 3 to call subcommands instead of containing rendering templates. Remove the ASCII table template, column layout rules, and counting logic. Keep the scenario routing (A/B/C) and action parsing in the LLM — those are decision tasks.

**Step 2 (status table):** Remove the ~60 lines of table template, legend, and formatting rules (install.md lines 82-131). Replace with a call to `render-status-table` and a directive to display the output verbatim.

**Step 3 (tool picker):** Currently, Scenario A option [2] "Select specific tools" has no sub-menu specification — the LLM freestyles the presentation. Additionally, in Scenarios B and C, users can type tool names at the main prompt but have no numbered reference. Add `render-tool-picker` + `resolve-tool-selection` calls:

```
Run: python3 "$MG_INSTALL_LIB" render-tool-picker --input /tmp/mg-scan-status.json
Display verbatim. Get user response, then:
Run: python3 "$MG_INSTALL_LIB" resolve-tool-selection --input /tmp/mg-scan-status.json --selection "<response>"
Use the returned tool list.
```

The tool picker is invoked in Scenario A option [2]. For Scenarios B and C, it is invoked when the user types tool names or numbers instead of selecting a numbered menu option. The scenario A/B/C top-level menus themselves remain LLM-rendered (they are short, static, and reliable).

## Files Changed

- `install/scripts/mg-install-lib.py` — 3 new subcommands + argparse wiring
- `install/scripts/tests/test_mg_install_lib.py` — tests for each subcommand
- `install/commands/install.md` — simplify Steps 2 and 3
- `.claude/commands/mg/install.md` — deployed copy (keep in sync)

## Context from v1.1 session analysis

These issues were found during a real install of `permission-hooks` to `road-runner`:
- "Available: 9" displayed when 10 tools were available (LLM arithmetic error)
- Second run of the same install showed unnumbered tool list, forcing user to type names
- Both runs showed slightly different table formatting (column widths, separator styles)

## Out of Scope

- Action menu rendering (Step 3 scenario A/B/C) — these are short, static, and the LLM renders them reliably enough
- Summary rendering (Step 8) — low variance, not worth the complexity
- Any changes to the install flow logic itself
