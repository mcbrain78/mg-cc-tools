---
phase: 10-create-a-renderer-for-the-install-command
verified: 2026-03-20T12:00:00Z
status: passed
score: 8/8 must-haves verified
---

# Phase 10: Create a Renderer for the Install Command — Verification Report

**Phase Goal:** Move the install command's status table (Step 2) and tool picker (Step 3) rendering from LLM-generated output to deterministic Python subcommands in mg-install-lib.py, eliminating miscounted summaries, misaligned columns, and inconsistent tool picker formatting
**Verified:** 2026-03-20T12:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | render-status-table produces a three-tier table (standard, optional, excluded) with aligned columns, summary counts scoped to non-excluded tools, status legend, and version transition annotations | VERIFIED | `render_status_table()` at line 857 in mg-install-lib.py; 9 substantive tests in TestRenderStatusTable confirm three-tier layout, dot/dashed separators, checkmark, star marker, version annotation, header format, and status legend; 29/29 tests pass |
| 2 | render-tool-picker produces a sequentially numbered list of non-excluded tools with Standard/Optional section headers and status annotations for non-available tools | VERIFIED | `render_tool_picker()` at line 954; tests in TestRenderToolPicker confirm section headers, sequential numbering, status annotations, excluded filter, footer line; 29/29 tests pass |
| 3 | resolve-tool-selection parses numbers, ranges, names, mixed input, and 'all' — returning a JSON list of tool names or an error JSON for invalid input | VERIFIED | `resolve_tool_selection()` at line 1010; TestResolveToolSelection covers all six input types including out-of-range error and unrecognized name error; 29/29 tests pass |
| 4 | render-tool-picker and resolve-tool-selection share a single _get_ordered_tools() function for consistent numbering | VERIFIED | `_get_ordered_tools()` defined once at line 820; called at line 961 (render_tool_picker) and line 1021 (resolve_tool_selection); TestGetOrderedTools confirms standard-first then optional, alphabetical within tiers, excluded filtered |
| 5 | install.md Step 2 calls render-status-table and directs the LLM to display output verbatim, with no inline table template or formatting rules | VERIFIED | Lines 84-88 of install.md: `python3 "$MG_INSTALL_LIB" render-status-table --input /tmp/mg-scan-status.json` followed by "Display the output verbatim — do not modify, reformat, or summarize it." No table template or column layout rules present anywhere in Step 2 |
| 6 | install.md Step 3 uses render-tool-picker and resolve-tool-selection for the "Select specific tools" sub-flow in Scenario A option [2] and when users type tool names/numbers in Scenarios B/C | VERIFIED | Lines 131-141: render-tool-picker and resolve-tool-selection called under "If user selects [2]"; lines 176-180: resolve-tool-selection with render-tool-picker fallback for Scenarios B/C name/number input |
| 7 | Scenario A/B/C top-level action menus remain as LLM-rendered plain text prompts (not moved to Python) | VERIFIED | Lines 119-127 (Scenario A), 143-154 (Scenario B), 156-166 (Scenario C) are all plain text blocks with [1]/[2]/[3] options — no Python subcommand calls replacing the menus |
| 8 | install/commands/install.md and .claude/commands/mg/install.md are identical | VERIFIED | `diff install/commands/install.md .claude/commands/mg/install.md` produces no output — files are byte-identical |

**Score:** 8/8 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `install/scripts/mg-install-lib.py` | Three new subcommands: render-status-table, render-tool-picker, resolve-tool-selection; contains _get_ordered_tools | VERIFIED | All three subcommands present; _get_ordered_tools defined at line 820 and wired in argparse at lines 1265-1292; +322 lines of implementation |
| `install/scripts/tests/test_mg_install_lib.py` | Test classes covering all three subcommands; contains TestRenderStatusTable | VERIFIED | TestRenderStatusTable (line 1825), TestRenderToolPicker (line 1974), TestResolveToolSelection (line 2070), TestGetOrderedTools (line 2228); 29 new tests, all passing |
| `install/commands/install.md` | Simplified Step 2 and Step 3 using Python subcommands | VERIFIED | Step 2 is 4 lines (scan-status call + render-status-table call + verbatim directive); Step 3 has render-tool-picker and resolve-tool-selection for specific-tool flows |
| `.claude/commands/mg/install.md` | Deployed copy of install.md, kept in sync | VERIFIED | Byte-identical to source (confirmed via diff) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `mg-install-lib.py::_get_ordered_tools` | render_tool_picker and resolve_tool_selection | shared function call | WIRED | _get_ordered_tools defined at line 820; called at line 961 in render_tool_picker and line 1021 in resolve_tool_selection |
| `mg-install-lib.py::cmd_render_status_table` | argparse main() | set_defaults(func=cmd_render_status_table) | WIRED | p_render_table.set_defaults(func=cmd_render_status_table) at line 1272 |
| `install/commands/install.md Step 2` | mg-install-lib.py render-status-table | python3 $MG_INSTALL_LIB render-status-table --input | WIRED | Line 85: `python3 "$MG_INSTALL_LIB" render-status-table --input /tmp/mg-scan-status.json` |
| `install/commands/install.md Step 3` | mg-install-lib.py render-tool-picker + resolve-tool-selection | python3 $MG_INSTALL_LIB render-tool-picker --input | WIRED | Line 132: render-tool-picker call; line 138: resolve-tool-selection call; line 177: resolve-tool-selection for B/C |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| INST-35 | 10-01-PLAN.md | Running `mg-install-lib.py render-status-table` with scan-status JSON produces a formatted three-tier status table on stdout | SATISFIED | render_status_table() at line 857; CLI handler at line 1171; argparse wiring at line 1265; 9 tests in TestRenderStatusTable all pass |
| INST-36 | 10-01-PLAN.md | Running `mg-install-lib.py render-tool-picker` with scan-status JSON produces a numbered tool list on stdout with section headers | SATISFIED | render_tool_picker() at line 954; CLI handler at line 1178; argparse wiring at line 1274; TestRenderToolPicker tests all pass |
| INST-37 | 10-01-PLAN.md | Running `mg-install-lib.py resolve-tool-selection` with scan-status JSON and user text produces a JSON list of resolved tool names | SATISFIED | resolve_tool_selection() at line 1010; CLI handler at line 1185; argparse wiring at line 1283; TestResolveToolSelection tests cover all input formats |
| INST-38 | 10-01-PLAN.md | render-tool-picker and resolve-tool-selection share a single internal ordering function (standard-first, then optional, excluding excluded) | SATISFIED | _get_ordered_tools() at line 820 is the sole ordering function; called by both render_tool_picker (line 961) and resolve_tool_selection (line 1021); TestGetOrderedTools confirms behavior |
| INST-39 | 10-02-PLAN.md | install.md Step 2 calls render-status-table and displays output verbatim, replacing the inline template | SATISFIED | install.md lines 84-88 contain the subcommand call and verbatim directive; no inline table template, example table, or column layout rules remain |
| INST-40 | 10-02-PLAN.md | install.md Step 3 uses render-tool-picker and resolve-tool-selection for the "Select specific tools" sub-flow | SATISFIED | Lines 131-141 (Scenario A [2] sub-flow) and lines 176-180 (B/C resolver with fallback) are present in install.md |
| INST-41 | 10-02-PLAN.md | Scenario A/B/C top-level action menus remain LLM-rendered (not moved to Python) | SATISFIED | All three scenario menus are plain text blocks in install.md; none replaced by Python subcommand calls |
| INST-42 | 10-01-PLAN.md | Pytest tests cover all three new subcommands (render-status-table, render-tool-picker, resolve-tool-selection) | SATISFIED | 29 tests across TestRenderStatusTable, TestRenderToolPicker, TestResolveToolSelection, TestGetOrderedTools; all 29 pass; 84 total tests pass in install/scripts/tests/ with zero regressions |

All 8 requirements from both plans accounted for. No orphaned requirements — REQUIREMENTS.md traceability table maps exactly INST-35 through INST-42 to Phase 10.

---

### Anti-Patterns Found

No anti-patterns found. All three subcommand implementations are substantive (render_status_table is 87 lines, render_tool_picker is 49 lines, resolve_tool_selection is 73 lines). No TODO/FIXME/placeholder stubs. No empty return bodies. No console.log-only handlers.

---

### Human Verification Required

None. All must-haves are programmatically verifiable:

- Three subcommands exist and have substantive implementations
- Tests are present, substantive, and passing (84/84 in install tests)
- Key links are verified via grep
- Source and deployed install.md are byte-identical
- Scenario menus confirmed as plain text (not Python calls)

---

### Gaps Summary

No gaps. All 8 observable truths verified. Phase goal fully achieved.

The install command's Step 2 status table and Step 3 tool picker rendering are now handled by deterministic Python subcommands rather than LLM-generated output. The shared `_get_ordered_tools()` function guarantees consistent numbering between the picker and resolver. The deployed copy of install.md is byte-identical to the source.

---

_Verified: 2026-03-20T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
