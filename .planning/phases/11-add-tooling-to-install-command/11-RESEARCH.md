# Phase 11: Add Tooling to Install Command - Research

**Researched:** 2026-03-20
**Domain:** Python CLI subcommands, LLM prompt refactoring, deterministic orchestration
**Confidence:** HIGH

## Summary

This phase refactors the install command from a 475-line LLM-driven state machine into a thin orchestrator backed by 7 new Python subcommands (plus 2 modifications to existing ones). All deterministic logic -- scenario selection, action mapping, install planning, result tracking, summary rendering -- moves to Python. The LLM's only jobs become: echo output, collect input, spawn agents. There is one deliberate behavior change: Scenario B expanded to include corrupt/adopted statuses.

The existing codebase at `install/scripts/mg-install-lib.py` (1305 lines, 8 subcommands) and `install/scripts/tests/test_mg_install_lib.py` (2316 lines, 85 tests) provides all the patterns needed. Every new subcommand follows established conventions: `--input` for scan-status JSON, `--output` for file-based I/O, `print()` for rendered output, `json.dump()` to stdout for machine-readable data. The test suite uses subprocess invocation (`_run()` helper), `_make_tool()` fixture builder, and `_make_scan_status_fixture()` for renderer tests.

**Primary recommendation:** Implement in three waves -- (1) core scenario logic + action subcommands, (2) install-plan/record-result/renderers, (3) install.md prompt rewrite + deployed copy sync.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Auto-adopt via `--auto-adopt` flag on scan-status (replaces Step 2b entirely)
- `render-action-menu` subcommand with shared `_determine_scenario()` helper
- `resolve-action` subcommand using same shared `_determine_scenario()` helper
- `get-install-plan` subcommand reading target from scan-status JSON
- `render-preflight` subcommand (existing `preflight` gains `--output` support)
- `record-result` subcommand with append-only JSON file pattern
- `render-summary` subcommand with `--results`, `--input`, `--preflight` arguments
- `render-validation` subcommand for validation result formatting
- Shared scenario logic: `render-action-menu` and `resolve-action` MUST use single `_determine_scenario()`
- Prompt consolidation: single rendering rule replaces per-subcommand echo instructions
- CLI argument convention: `--input <path>` for scan-status across all subcommands
- Per-target temp file directories: `/tmp/mg-install-<target-basename>/`
- Stdlib-only constraint: no pip dependencies
- Scenario B triggers on corrupt and adopted statuses (behavior change from v1.2)
- What stays in prompt: Step 1 target selection, Step 3 edit standard list, Step 5 capability check, Step 6 agent spawning/marker parsing/stop-on-error, free text fallback
- What gets deleted from prompt: three scenario templates, option-to-action mapping, Step 2b adoption, per-tool pattern determination, preflight formatting, summary construction, validation formatting, per-subcommand echo instructions, hardcoded /tmp paths

### Claude's Discretion
- Internal function organization within mg-install-lib.py (helper placement, private function naming)
- Test structure and fixture design for new subcommands
- Exact formatting of render-preflight output (PASS/FAIL markers, grouping style)
- Exact formatting of render-validation output (PASS/WARNING layout, issue details)
- Exact formatting of render-summary output (column widths, separators, capability section layout)
- How to structure the install.md rewrite (section ordering, comment placement)
- Argparse wiring details for new subcommands

### Deferred Ideas (OUT OF SCOPE)
- Edit Standard Install List extraction to Python -- stays in prompt for now (~37 lines, low usage)
- Changes to install.sh scripts -- not in scope
- Changes to tool.toml format -- not in scope
- Verify-generate feedback loop -- separate work item
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INST-43 | `scan-status` gains `--auto-adopt` flag | Modify existing `scan_status()` + `cmd_scan_status()`: when flag set and manifest missing, call `adopt_tools()` before computing statuses. Add `auto_adopted` field to output. Existing `adopt_tools()` at line 739 provides the logic. |
| INST-44 | `render-action-menu` produces correct scenario menu | New subcommand using `_determine_scenario()` shared helper. Three scenario templates with dynamic count computation. Output plain text to stdout via `print()`. |
| INST-45 | `resolve-action` maps selection to action+tools | New subcommand using same `_determine_scenario()`. Maps menu numbers per scenario to `{"action": "...", "tools": [...]}`. Falls back to `resolve_tool_selection()` for non-menu input. |
| INST-46 | `get-install-plan` produces JSON install plan | New subcommand reading scan-status JSON. Determines pattern from `has_install_sh`/`post_install`. Pre-computes `expected_action` from status. Includes `commands` list. Uses `--output` for file output. |
| INST-47 | `render-preflight` formats preflight results | New subcommand + modify existing `cmd_preflight()` to support `--output`. Render uses PASS/FAIL markers, required/optional grouping, summary counts. |
| INST-48 | `record-result` appends to install-results file | New subcommand. Reads install plan JSON for tool's `commands` and `expected_action`. Append-only: read array, append entry, rewrite file. Creates file with `[]` if missing. |
| INST-49 | `render-summary` formats final summary table | New subcommand with three inputs (`--results`, `--input`, `--preflight`). Formats action column, command filenames, counts. Merges capability data from preflight if provided. |
| INST-50 | `render-validation` formats validation results | New subcommand reading validate JSON. PASS/WARNING output with issue details and count. |
| INST-51 | Scenario B triggers on corrupt and adopted | Implemented in `_determine_scenario()`: condition is `update > 0 or modified > 0 or corrupt > 0 or adopted > 0`. Tests verify this. |
| INST-52 | `install.md` rewritten as thin orchestrator | Complete rewrite of `install/commands/install.md` from ~475 lines to <250 lines. LLM only echoes output, collects input, spawns agents. Zero conditional rendering. |
| INST-53 | Shared `_determine_scenario()` function | Single private function used by both `render_action_menu()` and `resolve_action()`. Returns scenario letter ("A"/"B"/"C") from scan_data summary counts. |
| INST-54 | Consolidated rendering rule for all render-* subcommands | Single directive at top of install.md: render-* output echoed verbatim as fenced code blocks; other subcommands output JSON not echoed. |
| INST-55 | Consistent `--input` CLI argument convention | All subcommands reading scan-status use `--input <path>`. render-summary uses `--input`, `--results`, `--preflight`. |
| INST-56 | Per-target temp file directories | Python auto-creates `/tmp/mg-install-<target-basename>/` when writing first `--output` file. Target basename from path. |
| INST-57 | All new code stdlib-only | No pip dependencies. Uses only: argparse, json, os, sys, re, pathlib, hashlib, tempfile, datetime, fcntl, subprocess, tomllib. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.11+ | All implementation | Locked decision: stdlib-only constraint |
| argparse | stdlib | CLI subcommand parsing | Already used for all 8 existing subcommands |
| json | stdlib | File-based I/O contract | Established pattern throughout codebase |
| tomllib | 3.11+ stdlib | tool.toml parsing | Already used, drives >=3.11 floor |
| pytest | dev dep | Test framework | Already configured in pyproject.toml [dev] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| os.path / pathlib | stdlib | Path manipulation | Per-target temp dir creation, basename extraction |
| re | stdlib | Input parsing | resolve-action number/range detection (pattern from resolve_tool_selection) |
| tempfile | stdlib | Atomic writes | Already used in write_manifest_atomic; not needed for new subcommands (sequential, no locking) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib argparse | click/typer | Would violate stdlib-only constraint |
| json file I/O | sqlite | Overkill for sequential append-only pattern |
| print() for rendering | rich/colorama | Would violate stdlib-only constraint; ANSI not needed per project conventions |

**Installation:**
No new dependencies. Existing `pip install -e ".[dev]"` provides pytest and ruff.

## Architecture Patterns

### Existing Project Structure (unchanged)
```
install/
├── commands/
│   └── install.md           # LLM instruction prompt (rewrite target)
├── scripts/
│   ├── mg-install-lib.py    # All subcommands (1305 lines, growing to ~2000+)
│   └── tests/
│       ├── __init__.py
│       └── test_mg_install_lib.py  # All tests (2316 lines, growing to ~3500+)
└── tool.toml
```

### Pattern 1: Subcommand Implementation Pattern
**What:** Each subcommand is a pure function + a CLI handler + argparse wiring.
**When to use:** Every new subcommand follows this three-layer pattern.
**Example:**
```python
# Source: existing mg-install-lib.py lines 862-953 (render_status_table)

# Layer 1: Pure logic function
def render_action_menu(scan_data):
    """Render scenario-appropriate action menu to stdout."""
    scenario = _determine_scenario(scan_data)
    # ... compute counts, print menu ...

# Layer 2: CLI handler
def cmd_render_action_menu(args):
    """CLI handler for render-action-menu."""
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    render_action_menu(scan_data)

# Layer 3: Argparse wiring in main()
p_menu = sub.add_parser("render-action-menu", help="...")
p_menu.add_argument("--input", required=True, help="Path to scan-status JSON")
p_menu.set_defaults(func=cmd_render_action_menu)
```

### Pattern 2: File-Based I/O with --output Flag
**What:** Subcommands write full data to file, compact summary to stdout.
**When to use:** Any subcommand whose full output would bloat LLM context.
**Example:**
```python
# Source: existing cmd_scan_status (lines 1096-1129)
# Pattern: --output writes file + compact stdout; without --output, full JSON to stdout

# For get-install-plan and preflight gaining --output:
if args.output:
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    # Compact summary to stdout
    compact = {"tool_count": len(result), "details": args.output}
    json.dump(compact, sys.stdout, indent=2)
    sys.stdout.write("\n")
else:
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
```

### Pattern 3: Shared Helper with Single Source of Truth
**What:** Internal function shared by multiple subcommands to prevent logic divergence.
**When to use:** When two subcommands must agree on classification (e.g., scenario determination).
**Example:**
```python
# Source: existing _get_ordered_tools (line 823) shared by picker + resolver

def _determine_scenario(scan_data):
    """Determine install scenario from scan-status summary.

    Returns "A", "B", or "C". Used by both render_action_menu and resolve_action.
    """
    summary = scan_data.get("summary", {})
    installed_total = summary.get("installed_total", 0)
    if installed_total == 0:
        return "A"
    if (summary.get("update", 0) > 0 or summary.get("modified", 0) > 0
            or summary.get("corrupt", 0) > 0 or summary.get("adopted", 0) > 0):
        return "B"
    return "C"
```

### Pattern 4: Renderer Output (print to stdout)
**What:** Render subcommands use `print()` for human-readable output, never `json.dump()`.
**When to use:** All `render-*` subcommands.
**Example:**
```python
# Source: existing render_status_table (lines 862-953)
# Key: print() for display, no JSON mixing, consistent indentation
print("Preflight checks:")
print()
print(f"  [PASS] python3    {version}    (required)")
print(f"  [FAIL] ruff       missing     (optional: codebase-health degraded)")
print()
print(f"  Required: {req_pass}/{req_total} passed")
```

### Pattern 5: Per-Target Temp Directories
**What:** Inter-step files scoped to target project basename to prevent collision.
**When to use:** All `--output` file paths in the prompt.
**Example:**
```python
# Derive temp dir from target path
def _get_temp_dir(target_path):
    """Get per-target temp directory for inter-step files."""
    basename = os.path.basename(os.path.normpath(target_path))
    temp_dir = os.path.join(tempfile.gettempdir(), f"mg-install-{basename}")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir
```

### Anti-Patterns to Avoid
- **Duplicating scenario logic:** render-action-menu and resolve-action MUST share `_determine_scenario()`. Duplicating this is the exact class of bug this refactor eliminates.
- **Returning render output as JSON:** render-* subcommands print plain text, never JSON. The LLM echoes it verbatim.
- **LLM computing tool lists:** The LLM never builds tool lists from scan-status fields. resolve-action and get-install-plan do this.
- **LLM providing command filenames:** record-result reads the install plan for command filenames. The LLM only passes `--tool` and `--success`/`--failed`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Scenario selection | LLM if/elif in prompt | `_determine_scenario()` | LLM misroutes scenarios; Python is deterministic |
| Tool list computation | LLM reading summary counts | `resolve_action()` pre-computed lists | LLM omits tools, miscounts; Python filters are exact |
| Install pattern determination | LLM checking has_install_sh/post_install per tool | `get_install_plan()` | LLM applies wrong pattern; Python lookup is reliable |
| Result tracking across install loop | LLM reconstructing from memory | `record_result()` append-only file | LLM forgets tools, swaps actions; file is authoritative |
| Summary rendering | LLM formatting table from memory | `render_summary()` from files | LLM truncates, drops columns; Python renders complete output |

**Key insight:** The LLM is unreliable at maintaining state across multi-step flows. Every piece of state that flows between steps should be in a JSON file, not in the LLM's context.

## Common Pitfalls

### Pitfall 1: Scenario Logic Drift
**What goes wrong:** render-action-menu shows 5 options for Scenario B but resolve-action maps as if there were 4 (or different 5).
**Why it happens:** The scenario classification or option mapping is duplicated instead of shared.
**How to avoid:** `_determine_scenario()` is the single source of truth. Both render-action-menu and resolve-action call it. Test that the same scan-status fixture produces matching scenario classification in both subcommands.
**Warning signs:** A test passes for render-action-menu but fails for resolve-action on the same input.

### Pitfall 2: --output Directory Doesn't Exist
**What goes wrong:** `--output /tmp/mg-install-road-runner/scan-status.json` fails because `/tmp/mg-install-road-runner/` doesn't exist yet.
**Why it happens:** The first subcommand to write an `--output` file creates the per-target directory, but if it's scan-status, the existing `cmd_scan_status` uses `open()` without `os.makedirs()`.
**How to avoid:** Add `os.makedirs(os.path.dirname(args.output), exist_ok=True)` before writing to `--output` in every CLI handler that supports it. This is idempotent and safe.
**Warning signs:** First install to a new target fails; subsequent installs work (because another process created `/tmp/`).

### Pitfall 3: Auto-Adopt Changes Scan-Status Output Shape
**What goes wrong:** With `--auto-adopt`, scan-status output gains an `auto_adopted` field that downstream consumers don't expect.
**Why it happens:** Adding a field to existing output without updating compact summary and tests.
**How to avoid:** Add `auto_adopted` to both full output and compact summary. Update existing scan-status tests to verify backward compatibility when `--auto-adopt` is not used (field should be absent or empty list).

### Pitfall 4: record-result File Doesn't Exist on First Call
**What goes wrong:** First call to record-result tries to read a file that doesn't exist.
**Why it happens:** The install loop hasn't created the file yet.
**How to avoid:** record-result creates file with `[]` if not found, then appends. This is specified in CONTEXT.md and must be implemented.
**Warning signs:** First tool install succeeds but result isn't recorded.

### Pitfall 5: get-install-plan Tool Not in Scan-Status
**What goes wrong:** User explicitly names an excluded tool. resolve-action returns it in the tool list. get-install-plan can't find it in scan-status tools array.
**Why it happens:** resolve-tool-selection filters out excluded tools via `_get_ordered_tools`, but the user can type an excluded tool name directly.
**How to avoid:** get-install-plan should search the full tools array (not just ordered), and gracefully handle tools not found (error or skip with warning).

### Pitfall 6: Prompt Length Exceeds Target
**What goes wrong:** Rewritten install.md is 300+ lines instead of <250.
**Why it happens:** Keeping too much explanatory text, duplicating instructions from the rendering rule, or adding new edge case handling.
**How to avoid:** Write the prompt from scratch following the "run Python -> echo output -> get input -> run Python" pattern. Don't try to incrementally edit the existing 475-line prompt.

### Pitfall 7: Deployed Copy Not Synced
**What goes wrong:** `install/commands/install.md` is updated but `.claude/commands/mg/install.md` is not (or vice versa).
**Why it happens:** Two files must contain identical content.
**How to avoid:** Copy one to the other as the final step. Verify with diff.

## Code Examples

### _determine_scenario() -- Shared Scenario Logic
```python
# New shared helper
def _determine_scenario(scan_data):
    """Determine install scenario from scan-status data.

    Returns:
        "A" if nothing installed (installed_total == 0)
        "B" if some tools need attention (update/modified/corrupt/adopted > 0)
        "C" if all installed tools are current
    """
    summary = scan_data.get("summary", {})
    installed_total = summary.get("installed_total", 0)
    if installed_total == 0:
        return "A"
    if (summary.get("update", 0) > 0
            or summary.get("modified", 0) > 0
            or summary.get("corrupt", 0) > 0
            or summary.get("adopted", 0) > 0):
        return "B"
    return "C"
```

### render_action_menu() -- Menu Rendering with Dynamic Counts
```python
def render_action_menu(scan_data):
    """Render scenario-appropriate action menu to stdout."""
    scenario = _determine_scenario(scan_data)
    tools = scan_data.get("tools", [])
    summary = scan_data.get("summary", {})

    # Compute dynamic counts
    attention_count = (summary.get("update", 0) + summary.get("modified", 0)
                       + summary.get("corrupt", 0) + summary.get("adopted", 0))
    standard_available = sum(
        1 for t in tools
        if t["status"] == "available" and t["standard"] and not t["excluded"]
    )
    standard_total = sum(
        1 for t in tools if t["standard"] and not t["excluded"]
    )

    print("What would you like to do?")
    print()

    if scenario == "A":
        print(f"  [1] Install all standard tools ({standard_total} tools) (recommended)")
        print("  [2] Select specific tools")
        print("  [3] Edit standard install list")
        print()
        print("Type a number, or tool names separated by commas:")
    elif scenario == "B":
        print(f"  [1] Fix/update {attention_count} tools needing attention (recommended)")
        print("  [2] Fix/update + install all missing standard")
        print(f"  [3] Install missing standard only ({standard_available} tools)")
        print("  [4] Edit standard install list")
        print("  [5] Check capabilities only")
        print()
        print("Type a number, tool names, or 'all':")
    elif scenario == "C":
        print(f"  [1] Install remaining {standard_available} standard tools")
        print("  [2] Reinstall all")
        print("  [3] Edit standard install list")
        print("  [4] Check capabilities only")
        print()
        print("Type a number, tool names, or 'all':")
```

### resolve_action() -- Action Resolution
```python
def resolve_action(scan_data, selection_text):
    """Resolve user's menu selection to action and tool list.

    Returns dict: {"action": "install", "tools": [...]} or
                  {"action": "select_specific"} or
                  {"action": "edit_standard"} or
                  {"action": "check_capabilities"} or
                  {"error": "..."}
    """
    scenario = _determine_scenario(scan_data)
    tools = scan_data.get("tools", [])
    summary = scan_data.get("summary", {})
    stripped = selection_text.strip()

    # Try to match a menu number
    if stripped.isdigit():
        num = int(stripped)
        return _resolve_menu_option(scenario, num, tools, summary)

    # Not a menu number -- try resolve_tool_selection for names/ranges
    result = resolve_tool_selection(scan_data, selection_text)
    if "error" in result:
        return result
    return {"action": "install", "tools": result["tools"]}
```

### get_install_plan() -- Install Plan Generation
```python
def get_install_plan(scan_data, tool_names):
    """Generate install plan for given tools.

    Returns list of install instruction dicts.
    """
    target = scan_data.get("target", "")
    tools_by_name = {t["name"]: t for t in scan_data.get("tools", [])}
    plan = []

    for name in tool_names:
        tool = tools_by_name.get(name)
        if tool is None:
            continue

        has_sh = tool.get("has_install_sh", False)
        post_install = tool.get("post_install")

        # Determine pattern
        if has_sh and not post_install:
            pattern = "copy_only"
        elif has_sh and post_install:
            pattern = "copy_configure"
        else:
            pattern = "execute_only"

        # Determine expected action
        status = tool["status"]
        if status == "available":
            action = "installed"
        elif status in ("update", "modified", "corrupt", "adopted"):
            action = "updated"
        else:
            action = "reinstalled"

        if pattern in ("copy_configure", "execute_only"):
            action += " (configured)"

        # Build install command
        install_cmd = None
        if has_sh:
            install_cmd = f'bash ./{name}/install.sh --target "{target}/.claude"'

        plan.append({
            "tool": name,
            "pattern": pattern,
            "expected_action": action,
            "install_cmd": install_cmd,
            "post_install": f"{name}/{post_install}" if post_install else None,
            "commands": tool.get("commands", []),
        })

    return plan
```

### record_result() -- Append-Only Result Tracking
```python
def record_result(results_file, tool_name, success, plan_file):
    """Append install result for one tool to results file.

    Creates the file with [] if it doesn't exist.
    Reads plan file to look up expected_action and commands.
    """
    # Read install plan for tool's metadata
    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    tool_plan = next((p for p in plan if p["tool"] == tool_name), None)

    if success:
        entry = {
            "tool": tool_name,
            "action": tool_plan["expected_action"] if tool_plan else "installed",
            "commands": tool_plan["commands"] if tool_plan else [],
        }
    else:
        entry = {
            "tool": tool_name,
            "action": "failed",
            "commands": [],
        }

    # Read existing results or create empty
    if os.path.isfile(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            results = json.load(f)
    else:
        results = []

    results.append(entry)

    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        f.write("\n")
```

## State of the Art

| Old Approach (v1.2) | Current Approach (v1.3) | When Changed | Impact |
|---------------------|------------------------|--------------|--------|
| LLM selects scenario A/B/C from summary counts | `_determine_scenario()` + `render-action-menu` | Phase 11 | Eliminates wrong scenario routing |
| LLM maps option numbers to actions per scenario | `resolve-action` with shared scenario logic | Phase 11 | Eliminates option misinterpretation |
| LLM determines install pattern per tool | `get-install-plan` with pattern lookup | Phase 11 | Eliminates wrong pattern application |
| LLM reconstructs summary from memory | `record-result` + `render-summary` from files | Phase 11 | Eliminates forgotten/swapped results |
| LLM formats preflight/validation output | `render-preflight` + `render-validation` | Phase 11 | Eliminates truncation/formatting errors |
| LLM checks manifest_exists and runs adopt | `scan-status --auto-adopt` | Phase 11 | Eliminates skipped adoption step |
| Per-subcommand "echo verbatim" instructions | Single consolidated rendering rule | Phase 11 | Reduces prompt size, consistent behavior |
| Hardcoded /tmp/mg-*.json paths | Per-target `/tmp/mg-install-<basename>/` | Phase 11 | Prevents collision for concurrent sessions |
| Scenario B: update + modified only | Scenario B: update + modified + corrupt + adopted | Phase 11 | Corrupt/adopted tools get repair menu |

**Deprecated/outdated:**
- Step 2b manual adoption check: replaced by `--auto-adopt` flag
- Three inline scenario templates in install.md: replaced by `render-action-menu`
- Option-to-action mapping tables in prompt: replaced by `resolve-action`

## Open Questions

1. **get-install-plan compact stdout format**
   - What we know: `--output` writes full plan to file. CONTEXT.md says "Uses `--output` for file output (consistent with scan-status and validate)."
   - What's unclear: What compact summary should stdout return? The LLM needs enough to iterate the plan (tool names, patterns, post_install paths).
   - Recommendation: Compact stdout returns array of `{"tool": name, "pattern": pattern, "post_install": path_or_null}` -- enough to drive the install loop without full command lists.

2. **render-summary "Capabilities" section format**
   - What we know: Merges data from preflight JSON (LSP status, missing optional tools).
   - What's unclear: Exact formatting of capabilities section -- is it the same as the existing Step 5 output or a simplified version?
   - Recommendation: Match the existing Step 8 summary format from install.md -- `LSP: functional (plugin-name)` and `Missing optional tools: ruff, vulture (details)`.

3. **Per-target temp directory cleanup**
   - What we know: Files are created in `/tmp/mg-install-<basename>/` during a session.
   - What's unclear: Should old temp directories be cleaned up? What about stale files from aborted sessions?
   - Recommendation: Don't clean up. `/tmp` is cleaned by the OS on reboot. Overwriting on each new session is sufficient.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `.venv/bin/pytest`) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py --tb=short -q --no-header` |
| Full suite command | `.venv/bin/pytest --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INST-43 | scan-status --auto-adopt | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "auto_adopt" -x` | Wave 0 |
| INST-44 | render-action-menu output | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "render_action_menu" -x` | Wave 0 |
| INST-45 | resolve-action mapping | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "resolve_action" -x` | Wave 0 |
| INST-46 | get-install-plan output | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "install_plan" -x` | Wave 0 |
| INST-47 | render-preflight output | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "render_preflight" -x` | Wave 0 |
| INST-48 | record-result append | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "record_result" -x` | Wave 0 |
| INST-49 | render-summary output | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "render_summary" -x` | Wave 0 |
| INST-50 | render-validation output | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "render_validation" -x` | Wave 0 |
| INST-51 | Scenario B triggers on corrupt/adopted | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "scenario_b" -x` | Wave 0 |
| INST-52 | install.md thin orchestrator | manual-only | Manual: run `/mg:install` on a test target | N/A |
| INST-53 | Shared _determine_scenario | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "determine_scenario" -x` | Wave 0 |
| INST-54 | Consolidated rendering rule | manual-only | Manual: verify install.md has single rendering rule | N/A |
| INST-55 | --input CLI convention | unit | Covered by per-subcommand CLI tests | Wave 0 |
| INST-56 | Per-target temp directories | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "temp_dir" -x` | Wave 0 |
| INST-57 | Stdlib-only | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "stdlib" -x` OR manual review | N/A |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py --tb=short -q --no-header`
- **Per wave merge:** `.venv/bin/pytest --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `TestDetermineScenario` class -- tests for _determine_scenario shared helper
- [ ] `TestAutoAdopt` additions to existing `TestScanStatus` or new class -- tests for --auto-adopt flag
- [ ] `TestRenderActionMenu` class -- scenario A/B/C menu output tests
- [ ] `TestResolveAction` class -- menu option mapping + fallback to tool selection
- [ ] `TestGetInstallPlan` class -- pattern determination, expected_action, --output support
- [ ] `TestRenderPreflight` class -- PASS/FAIL formatting, required/optional grouping
- [ ] `TestRecordResult` class -- file creation, append, success/failed entries
- [ ] `TestRenderSummary` class -- action column, command filenames, capability merge
- [ ] `TestRenderValidation` class -- PASS/WARNING formatting, issue details
- [ ] Fixture: extended `_make_scan_status_fixture()` variants for Scenario A (nothing installed), Scenario B (with corrupt/adopted), Scenario C (all current)
- [ ] Fixture: `_make_preflight_fixture()` for preflight renderer tests
- [ ] Fixture: `_make_install_plan_fixture()` for record-result and render-summary tests
- [ ] `cmd_preflight` --output support tests (addition to existing `TestPreflight`)

## Sources

### Primary (HIGH confidence)
- `install/scripts/mg-install-lib.py` (1305 lines) -- all existing subcommand implementations, patterns, helpers
- `install/scripts/tests/test_mg_install_lib.py` (2316 lines, 85 tests) -- all test patterns, fixtures, helpers
- `install/commands/install.md` (475 lines) -- current prompt being replaced
- `.planning/phases/11-add-tooling-to-install-command/11-CONTEXT.md` -- locked decisions from user discussion
- `docs/work-queue/todo/install-command-v1.3/CONCEPT.md` -- detailed specifications with examples

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` -- project history confirming Phase 10 patterns (render subcommands, _get_ordered_tools)
- `.planning/REQUIREMENTS.md` -- requirement definitions INST-43 through INST-57

### Tertiary (LOW confidence)
- None -- all findings are from project source code and locked user decisions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- stdlib-only is a locked decision; existing patterns are established
- Architecture: HIGH -- all patterns are directly observed in the existing codebase (1305 lines of reference implementation)
- Pitfalls: HIGH -- identified from actual bugs mentioned in CONCEPT.md (scenario misrouting, skipped adoption, summary truncation)

**Research date:** 2026-03-20
**Valid until:** No expiration -- all findings are project-internal, no external dependency version concerns
