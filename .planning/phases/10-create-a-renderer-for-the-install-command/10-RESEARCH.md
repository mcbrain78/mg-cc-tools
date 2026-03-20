# Phase 10: Create a Renderer for the Install Command - Research

**Researched:** 2026-03-20
**Domain:** Python CLI rendering / argparse subcommands / text table formatting
**Confidence:** HIGH

## Summary

This phase adds three deterministic Python subcommands to `mg-install-lib.py` that replace LLM-generated rendering in the install command's Steps 2 and 3. The core problem is that LLMs are unreliable at reproducing exact text templates -- miscounting summary values, misaligning columns, and varying layout between runs. The solution is straightforward: Python functions that consume the existing `scan_status()` JSON output and produce formatted text to stdout.

The codebase already has all the infrastructure needed. `mg-install-lib.py` has an established argparse subcommand pattern (5 existing subcommands), a well-tested `scan_status()` function that produces the JSON these renderers consume, and a test suite with 55 passing tests using subprocess invocation against temp directories. The new subcommands are pure stdlib Python -- no new dependencies.

**Primary recommendation:** Add three subcommands (`render-status-table`, `render-tool-picker`, `resolve-tool-selection`) as pure functions consuming scan-status JSON, with a single shared `_get_ordered_tools()` helper to guarantee numbering consistency between picker and resolver.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- `render-status-table` reads full scan-status JSON (the `--output` file, not compact stdout summary)
- Output is formatted status table to stdout, ready for verbatim display
- Groups tools into three tiers: standard, optional (marked `*`), excluded -- with section headers and separators
- Computes summary line with correct counts scoped to non-excluded tools only
- Includes status legend at bottom
- Shows version transition annotations for update status (e.g., "Update (0.2.0 -> 0.3.0)")
- Column alignment is deterministic (computed from actual data widths)
- `render-tool-picker` reads full scan-status JSON, outputs numbered tool list to stdout with section headers
- Shows all non-excluded tools regardless of status -- covers both fresh install and reinstall/update scenarios
- Tools with non-available status get annotations: (Corrupt), (Modified), (Current), etc.
- Numbered sequentially across standard and optional sections (standard first)
- Filters out excluded tools
- `resolve-tool-selection` takes scan-status JSON + user's text response, outputs JSON list of resolved tool names
- Parses numbers ("2,9"), ranges ("1-3"), names ("permission-hooks"), mixed ("1-3, permission-hooks"), and "all"
- Returns error JSON for invalid input (unknown number, unrecognized name)
- `render-tool-picker` and `resolve-tool-selection` must use an identical tool ordering function
- Both derive the ordered list from the scan-status JSON tool array, filtered to non-excluded, grouped standard-first then optional
- This shared logic must be a single internal function, not duplicated across subcommands
- Step 2: remove ~60 lines of table template, legend, and formatting rules; replace with `render-status-table` call and "display verbatim" directive
- Step 3: add `render-tool-picker` + `resolve-tool-selection` calls for the "Select specific tools" sub-flow
- Tool picker invoked in Scenario A option [2]; for Scenarios B and C, invoked when user types tool names or numbers instead of a menu option
- Scenario A/B/C top-level menus remain LLM-rendered (short, static, reliable)
- Files changed: `install/scripts/mg-install-lib.py`, `install/scripts/tests/test_mg_install_lib.py`, `install/commands/install.md`, `.claude/commands/mg/install.md`

### Claude's Discretion
- Column width calculation algorithm (fixed padding vs dynamic)
- Unicode box-drawing characters vs ASCII for separators
- Whether `render-status-table` also accepts the mg-cc-tools version string as argument (for the header line) or reads it from the JSON
- Internal helper function naming and organization within mg-install-lib.py
- Test fixture design (inline JSON vs file-based)
- argparse subcommand naming convention (`render-status-table` vs `render_status_table`)

### Deferred Ideas (OUT OF SCOPE)
- Action menu rendering (Step 3 scenario A/B/C menus) -- short, static, LLM handles reliably
- Summary rendering (Step 8) -- low variance, not worth the complexity
- Any changes to the install flow logic itself
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INST-35 | `mg-install-lib.py render-status-table` with scan-status JSON produces a formatted three-tier status table on stdout | Scan-status JSON structure documented; table format from install.md template analyzed; column alignment and tier grouping patterns identified |
| INST-36 | `mg-install-lib.py render-tool-picker` with scan-status JSON produces a numbered tool list on stdout with section headers | Shared ordering function pattern; CONCEPT.md example format for numbering and sections |
| INST-37 | `mg-install-lib.py resolve-tool-selection` with scan-status JSON and user text produces a JSON list of resolved tool names | Input parsing patterns (numbers, ranges, names, mixed, "all") documented; error JSON format defined |
| INST-38 | render-tool-picker and resolve-tool-selection share a single internal ordering function | `_get_ordered_tools()` helper pattern documented; filters excluded, groups standard-first |
| INST-39 | install.md Step 2 calls render-status-table and displays output verbatim, replacing the inline template | Lines 82-131 of install.md identified for removal; replacement call pattern documented |
| INST-40 | install.md Step 3 uses render-tool-picker and resolve-tool-selection for the "Select specific tools" sub-flow | Integration points in Scenario A/B/C documented; when picker is invoked vs when LLM parses directly |
| INST-41 | Scenario A/B/C top-level action menus remain LLM-rendered | Deferred by design -- out of scope for Python rendering |
| INST-42 | Pytest tests cover all three new subcommands | Test pattern from existing 55 tests documented; subprocess invocation with temp directories |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (argparse, json, sys) | 3.11+ | CLI parsing, JSON I/O, stdout output | Already used by mg-install-lib.py; zero-dependency constraint |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| textwrap (stdlib) | 3.11+ | Potential use for text indentation | If needed for consistent indentation formatting |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual column alignment | `tabulate` pip package | Violates zero-dependency constraint; manual alignment is ~20 lines |
| f-string formatting | `str.format()` | f-strings preferred -- more readable, already used throughout codebase |

**Installation:**
```bash
# No new dependencies -- all stdlib
```

## Architecture Patterns

### Recommended Project Structure

No new files or directories needed. Changes are additions to existing files:

```
install/
├── scripts/
│   ├── mg-install-lib.py          # +3 subcommands, +1 shared helper, +3 cmd_ handlers
│   └── tests/
│       └── test_mg_install_lib.py  # +3 test classes
├── commands/
│   └── install.md                  # Simplified Steps 2 and 3
```

### Pattern 1: Subcommand Addition (established)

**What:** Each new renderer follows the existing pattern: a pure function that returns/prints data, a `cmd_*` CLI handler, and argparse wiring in `main()`.

**When to use:** All three new subcommands.

**Example (from existing code):**
```python
# 1. Pure function
def render_status_table(scan_data):
    """Render formatted status table from scan-status JSON."""
    # ... compute and print table ...

# 2. CLI handler
def cmd_render_status_table(args):
    """CLI handler for render-status-table."""
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    render_status_table(scan_data)

# 3. Argparse wiring in main()
p_render = sub.add_parser(
    "render-status-table",
    help="Render formatted status table from scan-status JSON",
)
p_render.add_argument("--input", required=True,
                      help="Path to scan-status JSON file")
p_render.set_defaults(func=cmd_render_status_table)
```

### Pattern 2: Shared Ordering Function

**What:** A single `_get_ordered_tools(tools)` function that both `render-tool-picker` and `resolve-tool-selection` use to establish the canonical numbered order.

**When to use:** Any time tool numbering must be consistent.

**Example:**
```python
def _get_ordered_tools(tools):
    """Return non-excluded tools in canonical order: standard first, then optional.

    Each tool retains its original dict from scan-status JSON.
    This is the SINGLE source of truth for tool numbering used by
    render-tool-picker and resolve-tool-selection.
    """
    standard = [t for t in tools if not t["excluded"] and t["standard"]]
    optional = [t for t in tools if not t["excluded"] and not t["standard"]]
    return standard + optional
```

### Pattern 3: Input via --input file (new for renderers)

**What:** Unlike existing subcommands that take `--source` and `--target` and compute data themselves, the renderers read pre-computed scan-status JSON from a file. This avoids re-scanning and ensures they render the exact same data the LLM already used for scenario routing.

**When to use:** All three new subcommands.

**Rationale:** The scan-status JSON is already written to `/tmp/mg-scan-status.json` in Step 2 of the install flow. The renderers consume this same file. No `--source` or `--target` needed.

### Pattern 4: resolve-tool-selection output format

**What:** Returns JSON to stdout, matching the existing subcommand output pattern.

**Example:**
```python
# Success case
{"tools": ["codebase-health", "create-docs", "permission-hooks"]}

# Error case
{"error": "Invalid selection: number 15 is out of range (1-11)"}
```

### Anti-Patterns to Avoid
- **Duplicating ordering logic:** The tool ordering MUST be a single `_get_ordered_tools()` function. Do NOT compute the order inline in both render-tool-picker and resolve-tool-selection.
- **Reading compact stdout summary:** The renderers need the FULL scan-status JSON (with `installed_version` and `current_version` fields). The compact stdout summary omits these. Always use `--input` pointing to the `--output` file from scan-status.
- **Hardcoding column widths:** Column widths must be computed from actual data. Tool names and descriptions vary in length across the 13 tools.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Column alignment | Manual spaces per line | Compute max widths, then f-string `:<width` formatting | Prevents misalignment when tool names/descriptions change |
| Unicode separator lines | Hardcoded separator strings | Compute width from column totals, then `"─" * width` | Adapts to dynamic column widths |
| Input parsing (numbers, ranges, names) | Custom character-by-character parser | Split on commas, then classify each token (is digit? contains `-`? is name?) | Simple, readable, handles edge cases |

**Key insight:** These are all deterministic text formatting tasks -- the whole point of this phase. Keep the Python simple and let the formatting be mechanical.

## Common Pitfalls

### Pitfall 1: Off-by-one in summary counts
**What goes wrong:** Summary line says "Installed: 6/9" but the count is wrong because excluded tools were included or non-excluded tools were missed.
**Why it happens:** The summary must count ONLY non-excluded tools in both numerator (installed) and denominator (total non-excluded).
**How to avoid:** Filter tools to `not t["excluded"]` before computing any summary counts. Use `summary` dict from scan-status JSON which already has correct counts -- but verify `installed_total` and `total` match non-excluded expectations.
**Warning signs:** Test with a mix of excluded/non-excluded tools and verify counts match.

### Pitfall 2: Tool ordering mismatch between picker and resolver
**What goes wrong:** User selects "2" in the tool picker but gets the wrong tool from resolve-tool-selection because the ordering differs.
**Why it happens:** The ordering logic is duplicated instead of shared.
**How to avoid:** Single `_get_ordered_tools()` function used by both. Test with mixed standard/optional tools and verify the number-to-name mapping is identical.
**Warning signs:** Tests that create the same tool set and compare picker output numbers against resolver resolution.

### Pitfall 3: Version transition display
**What goes wrong:** Status shows "Update" but doesn't include the version annotation "(0.2.0 -> 0.3.0)".
**Why it happens:** `installed_version` is only present in the FULL scan-status JSON (the `--output` file), not in the compact stdout summary. If the renderer reads the wrong source, version data is missing.
**How to avoid:** Always read from the full JSON file. Check for `installed_version is not None` before building version transition string.
**Warning signs:** Test with tools that have `status: "update"` and verify the version annotation appears.

### Pitfall 4: Ambiguous user input in resolve-tool-selection
**What goes wrong:** User types "1-3, permission-hooks" and the parser fails or misinterprets.
**Why it happens:** Mixed input combining numbers/ranges and names requires careful tokenization.
**How to avoid:** Split on commas first, strip whitespace from each token, then classify: if all digits -> number; if contains `-` with digits on both sides -> range; otherwise -> name lookup. Handle "all" as a special case before splitting.
**Warning signs:** Test with all input permutations: pure numbers, pure ranges, pure names, mixed, "all", invalid numbers, invalid names.

### Pitfall 5: Sync between install.md source and deployed copy
**What goes wrong:** `install/commands/install.md` is updated but `.claude/commands/mg/install.md` still has the old Step 2/3 content.
**Why it happens:** Two copies of the same file must be kept in sync manually.
**How to avoid:** After editing `install/commands/install.md`, copy the exact content to `.claude/commands/mg/install.md`. The CONTEXT.md explicitly lists both files as changed.
**Warning signs:** Diff the two files after changes.

### Pitfall 6: argparse subcommand naming
**What goes wrong:** Subcommand uses underscores (`render_status_table`) but install.md references hyphens (`render-status-table`).
**Why it happens:** Python identifiers use underscores but CLI conventions use hyphens.
**How to avoid:** Use hyphens in argparse (matching existing pattern: `scan-status`, `update-manifest`). The CLI handler function uses underscores (`cmd_render_status_table`). This matches the existing convention exactly.
**Warning signs:** All 5 existing subcommands use hyphens in argparse.

## Code Examples

Verified patterns from the existing codebase:

### Scan-Status JSON Structure (full output file)
```python
# Source: mg-install-lib.py scan_status() function, lines 317-412
{
    "mg_cc_tools_version": "0.3.0",
    "target": "/home/user/projects/road-runner",
    "manifest_exists": true,
    "tools": [
        {
            "name": "codebase-health",
            "description": "Scan, verify, and fix code health issues",
            "status": "current",           # current|update|modified|corrupt|available
            "installed_version": "0.3.0",  # None if available
            "current_version": "0.3.0",
            "changed_files": [],
            "commands": ["codebase-health.md"],
            "excluded": false,
            "standard": true,
            "has_install_sh": true,
            "post_install": null
        },
        # ... more tools
    ],
    "summary": {
        "total": 13,
        "installed_total": 6,
        "current": 4,
        "update": 1,
        "modified": 1,
        "corrupt": 0,
        "available": 5
    }
}
```

### Existing argparse wiring pattern
```python
# Source: mg-install-lib.py main(), lines 901-973
# All existing subcommands use hyphens: scan-status, update-manifest, preflight, validate, adopt
p_scan = sub.add_parser(
    "scan-status",
    help="Discover tools, compute checksums, compare with manifest",
)
p_scan.add_argument("--source", required=True, ...)
p_scan.add_argument("--target", required=True, ...)
p_scan.add_argument("--output", ...)
p_scan.set_defaults(func=cmd_scan_status)
```

### Existing test pattern (subprocess invocation)
```python
# Source: test_mg_install_lib.py, lines 1-27
SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "mg-install-lib.py",
)

def _run(args, **kwargs):
    """Run mg-install-lib.py with given args, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, SCRIPT_PATH] + args,
        capture_output=True, text=True, **kwargs,
    )

# Tests create temp dirs, build mock tool structures, then call _run([...])
```

### Target status table format (from install.md template)
```
mg-cc-tools v0.3.0 -> /home/user/projects/road-runner

  Tool                 Description                                       Status
  ─────────────────────────────────────────────────────────────────────────────────
  create-docs          Documentation pipeline (scan, generate, verify)    Update (0.2.0 -> 0.3.0)
  codebase-health      Scan, verify, and fix code health issues           ✓ Current
  debug-triage         GSD debug workflow with structured triage           Available
  ·
  data-provider  *     Research and map external data field sources        Available
  gsd-patches    *     Apply GSD methodology patches                       Available
  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
  install              mg-cc-tools installer (internal)                    Excluded
  cc-regression-test   Claude Code regression test harness (internal)      Excluded

  Installed: 6/9  |  Outdated: 1  |  Available: 3

  Status legend:
    ✓ Current       Installed, version and source files match
    Update          Installed, but newer version available (old -> new)
    Modified        Installed, same version, source files changed (N files)
    Corrupt         In manifest but command files missing from disk
    Available       Not yet installed
    Excluded        Internal tool, install by name only

  *  = optional tool (not included in "Install all standard")
     Edit the standard list with option [N] below
```

### Target tool picker format (from CONCEPT.md)
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

### Real tool data (13 tools as of 2026-03-20)
```
Standard (standard=true, exclude=false): 8 tools
  codebase-health, create-context, create-docs, debug-triage,
  new-milestone-gsd, session-analyzer, update-backlog

Optional (standard=false, exclude=false): 4 tools
  data-provider, gsd-patches, mg-gsd-wrappers, permission-hooks

Excluded (exclude=true): 2 tools
  cc-regression-test, install
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LLM renders status table from template | Python `render-status-table` produces exact output | Phase 10 (this phase) | Eliminates counting errors, alignment drift |
| LLM freestyles tool picker sub-menu | Python `render-tool-picker` produces numbered list | Phase 10 (this phase) | Consistent numbering, annotations |
| LLM parses user selection input | Python `resolve-tool-selection` parses deterministically | Phase 10 (this phase) | Handles numbers, ranges, names, "all" reliably |

**Deprecated/outdated:**
- The ~60-line table template in install.md Step 2 (lines 82-131) will be replaced by a single subcommand call
- The ad-hoc tool picker in Step 3 will be replaced by `render-tool-picker` + `resolve-tool-selection` calls

## Open Questions

1. **Column width algorithm: fixed padding vs dynamic**
   - What we know: There are 13 tools with names ranging from 7 chars ("install") to 17 chars ("cc-regression-test") and descriptions from 20 to 55 chars.
   - What's unclear: Whether to compute column widths per-render or use generous fixed padding.
   - Recommendation: **Compute dynamically** -- find max name length and max description length across tools, add 2-4 chars padding. This is ~5 lines of code and adapts if tools are added. The existing install.md template already specifies "column alignment is deterministic (computed from actual data widths)."

2. **Version string source for header line**
   - What we know: The header line format is `mg-cc-tools v0.3.0 -> /path/to/target`. Both `mg_cc_tools_version` and `target` are in the scan-status JSON.
   - What's unclear: Whether to read version from JSON or accept as separate argument.
   - Recommendation: **Read from JSON** -- it's already there as `mg_cc_tools_version`, no need for a separate argument. Simpler CLI interface.

3. **Separator characters: Unicode vs ASCII**
   - What we know: The existing install.md template uses Unicode (`─────`, `✓`, `·`). The session-analyzer outputs plain text (SAN-18).
   - What's unclear: Whether terminal compatibility matters for the install command.
   - Recommendation: **Use Unicode** -- the existing template already uses Unicode separators and the install command runs in Claude Code's terminal which supports Unicode. Match the established visual style.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `.venv/bin/activate`) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py --tb=short -q --no-header` |
| Full suite command | `source .venv/bin/activate && python3 -m pytest --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INST-35 | render-status-table produces three-tier table | unit | `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py -k TestRenderStatusTable -x` | Wave 0 |
| INST-36 | render-tool-picker produces numbered list | unit | `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py -k TestRenderToolPicker -x` | Wave 0 |
| INST-37 | resolve-tool-selection produces JSON tool list | unit | `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py -k TestResolveToolSelection -x` | Wave 0 |
| INST-38 | Shared ordering function | unit | `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py -k "test_ordering" -x` | Wave 0 |
| INST-39 | install.md Step 2 calls render-status-table | manual-only | Review install.md source -- LLM prompt, not executable code | N/A |
| INST-40 | install.md Step 3 uses picker + resolver | manual-only | Review install.md source -- LLM prompt, not executable code | N/A |
| INST-41 | Scenario menus remain LLM-rendered | manual-only | Verify install.md still contains scenario A/B/C text menus | N/A |
| INST-42 | Pytest tests cover all three subcommands | unit | `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py -k "TestRenderStatusTable or TestRenderToolPicker or TestResolveToolSelection" -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py --tb=short -q --no-header`
- **Per wave merge:** `source .venv/bin/activate && python3 -m pytest --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `TestRenderStatusTable` class in `test_mg_install_lib.py` -- covers INST-35
- [ ] `TestRenderToolPicker` class in `test_mg_install_lib.py` -- covers INST-36
- [ ] `TestResolveToolSelection` class in `test_mg_install_lib.py` -- covers INST-37, INST-38

*(Framework and test infrastructure already exists -- 55 tests passing. Only new test classes needed.)*

## Sources

### Primary (HIGH confidence)
- `install/scripts/mg-install-lib.py` -- full source code read, 978 lines, 5 existing subcommands analyzed
- `install/commands/install.md` -- full source read, 495 lines, Steps 2 and 3 template analyzed
- `install/scripts/tests/test_mg_install_lib.py` -- full source read, 1698 lines, 55 tests, 6 test classes
- `docs/work-queue/todo/install-command-v1.2/CONCEPT.md` -- design document with example formats
- All 13 `tool.toml` files -- real tool names, descriptions, exclude/standard flags verified
- `.planning/phases/10-create-a-renderer-for-the-install-command/10-CONTEXT.md` -- locked decisions

### Secondary (MEDIUM confidence)
- None needed -- this is an internal tool extension with all source code available

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all stdlib, existing patterns
- Architecture: HIGH -- follows established subcommand pattern exactly, all code reviewed
- Pitfalls: HIGH -- real-world issues documented in CONCEPT.md from actual session analysis

**Research date:** 2026-03-20
**Valid until:** Indefinite -- internal tool, no external dependency changes possible
