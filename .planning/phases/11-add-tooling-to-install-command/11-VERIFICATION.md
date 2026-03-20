---
phase: 11-add-tooling-to-install-command
verified: 2026-03-20T00:00:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 11: Add Tooling to Install Command — Verification Report

**Phase Goal:** Refactor the install command from a 475-line LLM-driven state machine into a thin orchestrator where all deterministic logic (scenario selection, action mapping, install planning, result tracking, summary rendering) lives in Python subcommands, with one deliberate behavior change (Scenario B expanded to include corrupt/adopted statuses)
**Verified:** 2026-03-20
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | `_determine_scenario` is a single shared function used by both `render-action-menu` and `resolve-action` | VERIFIED | Line 1136: `render_action_menu` calls `_determine_scenario(scan_data)`; line 1244: `resolve_action` calls `_determine_scenario(scan_data)`. One definition at line 1109. |
| 2 | Scenario B triggers on corrupt and adopted statuses (INST-51 behavior change) | VERIFIED | Lines 1121-1125: `_determine_scenario` checks `corrupt > 0 or adopted > 0` in addition to update/modified |
| 3 | `render-action-menu` produces correct Scenario A/B/C menu with dynamic counts | VERIFIED | Lines 1134-1174: function computes `attention_count`, `standard_available`, `standard_total` from tools array; prints scenario-appropriate 3/5/4-option menus |
| 4 | `resolve-action` maps menu selections to correct action + tool list for all 3 scenarios, with fallback to `resolve_tool_selection` for non-numeric input | VERIFIED | Lines 1235-1258: numeric branch delegates to `_resolve_menu_option`; non-numeric delegates to `resolve_tool_selection(scan_data, ...)` at line 1255 |
| 5 | `scan-status --auto-adopt` detects and adopts existing installations when no manifest, returning adopted tool names | VERIFIED | Lines 1490-1500: flag triggers `adopt_tools(args.source, args.target)` only when manifest is None; result stored in `auto_adopted` list; added to both file output and compact stdout |
| 6 | `get-install-plan` produces per-tool pattern, expected_action, install_cmd, post_install path, and commands list | VERIFIED | Lines 1266-1317: determines copy_only/copy_configure/execute_only pattern; computes expected_action with "(configured)" suffix; builds install_cmd string; includes commands list |
| 7 | `render-preflight` formats preflight results as human-readable PASS/FAIL with required/optional grouping | VERIFIED | Lines 1320-1350: prints `[PASS]`/`[FAIL]` per check with version/error detail, then "Required: N/M passed" and optional line only if optional checks exist |
| 8 | `record-result` appends per-tool success or failure to a results JSON file, creating the file if missing | VERIFIED | Lines 1353-1389: creates `[]` if file absent, reads plan for `expected_action` and commands, appends entry, rewrites file |
| 9 | `render-summary` formats final summary table from install results, scan-status, and optional preflight data | VERIFIED | Lines 1392-1458: header + target + counts + tool table + optional capabilities section from preflight |
| 10 | `render-validation` formats validation results as PASS/WARNING output | VERIFIED | Lines 1461-1477: clean path prints success message; issue path prints WARNING lines with count |
| 11 | `install.md` is a thin orchestrator under 250 lines with zero conditional rendering and a single display rule | VERIFIED | File is 244 lines. No `Scenario A/B/C` or `scenario ==` logic found. Single "Display Rule" section at line 21 covers all `render-*` subcommands. |
| 12 | All inter-step temp files use per-target `$TMP` directories, no hardcoded `/tmp/mg-` paths | VERIFIED | `_get_temp_dir` at line 153 produces `/tmp/mg-install-{basename}`; `install.md` defines `TMP="$MG_TMP_BASE/mg-install-$(basename "$TARGET_PATH")"` at line 43; grep confirmed no hardcoded paths in install.md |

**Score:** 12/12 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `install/scripts/mg-install-lib.py` | `_determine_scenario`, `render_action_menu`, `resolve_action`, `get_install_plan`, `render_preflight`, `record_result`, `render_summary`, `render_validation`, `_get_temp_dir`, `preflight --output` | VERIFIED | All 10 functions present (lines 153, 1109, 1134, 1235, 1266, 1320, 1353, 1392, 1461); 1885 lines total; all argparse wired in `main()` lines 1700-1881 |
| `install/scripts/tests/test_mg_install_lib.py` | Tests for all new subcommands and shared helper | VERIFIED | 11 new test classes: `TestDetermineScenario`, `TestRenderActionMenu`, `TestResolveAction`, `TestScanStatusAutoAdopt`, `TestGetTempDir`, `TestGetInstallPlan`, `TestPreflightOutput`, `TestRenderPreflight`, `TestRecordResult`, `TestRenderSummary`, `TestRenderValidation`; 66 Phase 11 tests, 151 total |
| `install/commands/install.md` | Thin orchestrator prompt for `/mg:install` referencing all new subcommands | VERIFIED | 244 lines; all 14 subcommands referenced; `--auto-adopt`, `render-action-menu`, `get-install-plan`, `render-validation`, `render-summary` all present |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `render_action_menu` | `_determine_scenario` | direct function call | WIRED | Line 1136: `scenario = _determine_scenario(scan_data)` |
| `resolve_action` | `_determine_scenario` | direct function call | WIRED | Line 1244: `scenario = _determine_scenario(scan_data)` |
| `resolve_action` | `resolve_tool_selection` | fallback for non-menu input | WIRED | Lines 1254-1258: non-numeric branch calls `resolve_tool_selection(scan_data, selection_text)` |
| `cmd_scan_status` | `adopt_tools` | conditional call when `--auto-adopt` and no manifest | WIRED | Lines 1490-1494: `if args.auto_adopt:` + `manifest is None` → `adopt_tools(args.source, args.target)` |
| `get_install_plan` | scan_data tools array | tool lookup by name | WIRED | Lines 1272, 1276: `tools_by_name = {t["name"]: t for ...}` then `tools_by_name.get(name)` |
| `record_result` | install plan JSON file | reads plan for expected_action and commands | WIRED | Lines 1360-1363: `open(plan_file)` → `json.load` → `next(p for p in plan if p["tool"] == tool_name)` |
| `render_summary` | install results + scan-status + preflight | three input files merged | WIRED | Lines 1676-1684: `cmd_render_summary` opens `args.results`, `args.input`, and optionally `args.preflight` |
| `cmd_preflight` | `--output` file | file-based I/O with compact stdout | WIRED | Lines 1548-1562: `args.output` branch writes full result to file, compact `{all_passed, check_count, details}` to stdout |
| `install.md Step 2` | `scan-status --auto-adopt` | bash command | WIRED | Line 51: `scan-status --source ./ --target "$TARGET_PATH" --output "$TMP/scan-status.json" --auto-adopt` |
| `install.md Step 3` | `render-action-menu` + `resolve-action` | bash commands | WIRED | Lines 67 and 73: both subcommands present with correct argument syntax |
| `install.md Step 6` | `get-install-plan` + `record-result` | bash commands | WIRED | Lines 174 and 203: both present with correct `--input`, `--tools`, `--output`, `--file`, `--tool`, `--plan` syntax |
| `install.md Step 7` | `render-validation` | bash command | WIRED | Line 218: `render-validation --input "$TMP/validate.json"` |
| `install.md Step 8` | `render-summary` | bash command | WIRED | Line 228: `render-summary --results ... --input ... --preflight ...` |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| INST-43 | 11-01 | `scan-status` gains `--auto-adopt` flag | SATISFIED | `--auto-adopt` argparse flag at line 1711; `cmd_scan_status` conditional adoption logic at lines 1490-1500 |
| INST-44 | 11-01 | `render-action-menu` produces correct scenario menu | SATISFIED | `render_action_menu` at line 1134; CLI handler at line 1620; argparse at line 1799 |
| INST-45 | 11-01 | `resolve-action` maps selection to action + tool list | SATISFIED | `resolve_action` at line 1235; CLI handler at line 1627; argparse at line 1807 |
| INST-46 | 11-02 | `get-install-plan` produces JSON install plan with per-tool fields | SATISFIED | `get_install_plan` at line 1266 covering all three patterns and expected_action computation |
| INST-47 | 11-02 | `render-preflight` formats preflight results; `preflight` gains `--output` | SATISFIED | `render_preflight` at line 1320; `cmd_preflight` `--output` branch at lines 1548-1562 |
| INST-48 | 11-02 | `record-result` appends per-tool success/failure to results JSON | SATISFIED | `record_result` at line 1353; mutually exclusive `--success`/`--failed` at lines 1851-1855 |
| INST-49 | 11-02 | `render-summary` formats final summary table | SATISFIED | `render_summary` at line 1392; reads results + scan-status + optional preflight |
| INST-50 | 11-02 | `render-validation` formats validation results as PASS/WARNING | SATISFIED | `render_validation` at line 1461 |
| INST-51 | 11-01 | Scenario B triggers on corrupt and adopted statuses | SATISFIED | `_determine_scenario` checks `corrupt > 0 or adopted > 0` at lines 1123-1124; `attention_statuses` set at line 1188 includes both |
| INST-52 | 11-03 | `install.md` rewritten as thin orchestrator | SATISFIED | 244 lines (from 475); zero conditional rendering; single display rule |
| INST-53 | 11-01 | `render-action-menu` and `resolve-action` share single `_determine_scenario()` | SATISFIED | One definition at line 1109; called at lines 1136 and 1244 |
| INST-54 | 11-03 | Single consolidated rendering rule for all `render-*` subcommands | SATISFIED | "Display Rule" section at install.md line 21-23 covers all `render-*` output uniformly |
| INST-55 | 11-01, 11-02 | All subcommands reading scan-status use `--input`; `render-summary` uses `--input`, `--results`, `--preflight` | SATISFIED | Verified in argparse definitions: all scan-status readers use `--input`; render-summary uses all three |
| INST-56 | 11-02 | Inter-step temp files use per-target subdirectories | SATISFIED | `_get_temp_dir` at line 153; `install.md` TMP variable at line 43; no hardcoded paths |
| INST-57 | 11-01, 11-02 | All new code is stdlib-only with no pip dependencies | SATISFIED | Imports (lines 18-32) are all stdlib: argparse, datetime, fcntl, hashlib, json, os, re, subprocess, sys, tempfile, tomllib |

All 15 requirements satisfied. No orphaned requirements.

---

## Anti-Patterns Found

None. No TODO/FIXME/PLACEHOLDER comments found in modified files. No empty implementations. No stub returns.

---

## Human Verification Required

### 1. Interactive install flow end-to-end

**Test:** Run `/mg:install` in a real target project, go through Scenario A (fresh install) selecting option 1, and verify the full 8-step flow completes correctly.
**Expected:** Tools install, summary table appears, validation runs with no issues.
**Why human:** Interactive prompts (AskUserQuestion, tool picker, preflight output display) require a live Claude session to test.

### 2. Edit Standard Install List sub-flow

**Test:** In Step 3, choose "edit_standard" and toggle tools on/off, then save and confirm scan re-runs.
**Expected:** `standard_overrides` written to manifest; re-scan reflects new standard flags; user returns to Step 3 menu.
**Why human:** This sub-flow is LLM-executed toggle logic with no Python subcommand — must be tested interactively.

### 3. Scenario B display (corrupt/adopted trigger)

**Test:** With a target that has an adopted tool (no manifest, files present), run `/mg:install` and verify Scenario B menu appears with correct attention count.
**Expected:** Menu shows "Fix/update N tools needing attention" where N includes adopted tools.
**Why human:** Requires a real target environment with specific file state.

---

## Summary

Phase 11 goal is fully achieved. All 15 requirements (INST-43 through INST-57) are satisfied.

The refactor delivered exactly what the goal stated:

- **10 new Python subcommands** replace all deterministic LLM logic: `_determine_scenario`, `render_action_menu`, `resolve_action`, `get_install_plan`, `render_preflight`, `record_result`, `render_summary`, `render_validation`, `_get_temp_dir`, plus `preflight --output` upgrade.
- **install.md reduced from 475 to 244 lines** (49% reduction) with zero conditional rendering — the three scenario menu templates, option-to-action mapping tables, Step 2b adoption check, per-tool pattern determination, and all formatting logic are gone.
- **Single display rule** replaces 5+ scattered "echo verbatim" instructions throughout the old prompt.
- **INST-51 behavior change** implemented correctly: `_determine_scenario` returns "B" when `corrupt > 0 or adopted > 0`, and the `_resolve_menu_option` `attention_statuses` set includes both.
- **151/151 tests pass** with no regressions; 66 new tests cover all Phase 11 additions.

---

_Verified: 2026-03-20_
_Verifier: Claude (gsd-verifier)_
