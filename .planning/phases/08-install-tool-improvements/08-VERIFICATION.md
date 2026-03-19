---
phase: 08-install-tool-improvements
verified: 2026-03-19T19:00:00Z
status: passed
score: 22/22 must-haves verified
re_verification: false
gaps:
  - truth: "Phase 8 requirement IDs are recorded in REQUIREMENTS.md with traceability to Phase 8"
    status: resolved
    reason: "REQUIREMENTS.md covers only phases 1-7 (60 requirements). All 22 Phase 8 requirement IDs (LIB-DISCOVER, LIB-TOML, LIB-CHECKSUMS, LIB-ADOPT, LIB-SCANSTATUS, TEMPLATE, DETECT, TIERS, POSTINSTALL-PERMHOOKS, POSTINSTALL-CCREGTEST, POSTINSTALL-GSDPATCHES, EXECUTEONLY, SNAPSHOT-MGWRAPPERS, SNAPSHOT-CREATECTX, STALE-CLEANUP, INSTALL-SEQUENTIAL, INSTALL-STOPONERROR, INSTALL-SUBAGENT, INSTALL-STATUSMARKER, INSTALL-EXECUTEONLY, INSTALL-ADOPT, INSTALL-TIERS) appear in ROADMAP.md and PLAN frontmatter but are absent from REQUIREMENTS.md."
    artifacts:
      - path: ".planning/REQUIREMENTS.md"
        issue: "Stops at Phase 7 (INST-01..INST-12). No Phase 8 section, no traceability rows for Phase 8 IDs."
    missing:
      - "Add Phase 8 requirements section to REQUIREMENTS.md with descriptions for all 22 IDs"
      - "Add traceability rows mapping each ID to Phase 8 in the Traceability table"
      - "Update coverage count from 60 to 82"
---

# Phase 8: Install Tool Improvements Verification Report

**Phase Goal:** Add two-stage install support to /mg:install: each tool can have an optional post-install.md that runs as a subagent after install.sh completes, enabling tools that need Claude Code intelligence for configuration (settings.json merges, interactive patch application) to be installed through the unified installer.

**Verified:** 2026-03-19T19:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification
**Score:** 21/22 must-haves verified

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | discover_tools() finds tools with only tool.toml (no install.sh required) | VERIFIED | Line 204: only checks `os.path.isfile(toml_path)`, no install.sh check. gsd-patches (no install.sh) discovered by scan-status (confirmed live). |
| 2 | read_tool_toml() returns post_install_script and detect_paths fields | VERIFIED | Lines 175-185: parses `[post_install]` and `[detect]` sections, returns `post_install_script` and `detect_paths`. |
| 3 | compute_tool_checksums() includes post-install.md and patches/**/*.md | VERIFIED | Line 49: `"patches/**/*.md"` in CHECKSUM_INCLUDE. Line 241: loop over `["install.sh", "post-install.md"]` for root files. |
| 4 | adopt_tools() detects via [detect].paths in addition to commands | VERIFIED | Lines 769-784: dual detection — `commands_detected OR detect_detected`, skip when both empty. |
| 5 | scan_status() includes post_install and has_install_sh fields per tool | VERIFIED | Lines 394-397: `has_install_sh` and `post_install` computed and stored in tool_info. Live scan-status confirms: gsd-patches `has_install_sh=False, post_install=post-install.md`. |
| 6 | scan_status() does not flag tools with empty commands list as corrupt | VERIFIED | Line 354: `if manifest_commands else True` guards corrupt check. Test `test_no_corrupt_for_empty_commands` passes. |
| 7 | All 55 tests pass (48 existing + 7 new) | VERIFIED | `55 passed in 2.95s` confirmed. |
| 8 | TEMPLATE-post-install.md exists with status marker pattern mandated | VERIFIED | File exists (install/TEMPLATE-post-install.md). Contains both `POST-INSTALL: SUCCESS` and `POST-INSTALL: FAILED: <brief reason>` markers. |
| 9 | 6 tools have [detect] sections in tool.toml | VERIFIED | Inline Python check passed: codebase-health, create-docs, data-provider, debug-triage, new-milestone-gsd, update-backlog all have `[detect]`. |
| 10 | permission-hooks has standard=false and [detect] in tool.toml | VERIFIED | `standard = false` at line 3. `[detect]` section present. `[post_install]` present. |
| 11 | gsd-patches has standard=false (not exclude=true) and [post_install] in tool.toml | VERIFIED | `standard = false` at line 3. No `exclude = true`. `[post_install]` present with `script = "post-install.md"`. |
| 12 | permission-hooks/post-install.md is self-contained with status markers, no shell placeholders | VERIFIED | 244 lines. Contains `POST-INSTALL: SUCCESS` and `POST-INSTALL: FAILED`. No `{SOURCE_DIR}`, `{HOOKS_DIR}`, or `$ARGUMENTS`. PreToolUse hook logic and permission-guard.py references present. |
| 13 | permission-hooks/install.sh no longer copies install-permission-hooks.md and has stale cleanup | VERIFIED | `COMMANDS=()` (empty). Stale cleanup block present at line 122 targeting `install-permission-hooks.md`. |
| 14 | cc-regression-test/post-install.md handles settings.json merge as self-contained subagent | VERIFIED | 114 lines. Contains intercept-trigger.py hook merge logic, idempotency check, `PreToolUse` handling. Status markers present. No `PYEOF`. |
| 15 | cc-regression-test/install.sh has no inline Python and preserves manifest update | VERIFIED | No `PYEOF` block. `update-manifest` call preserved at line 154. |
| 16 | mg-gsd-wrappers/install.sh copies snapshot to .claude/mg-gsd-wrappers/references/ with stale cleanup | VERIFIED | Lines 128-137: `mkdir -p "${TARGET_DIR}/mg-gsd-wrappers/references"`, copy, `STALE_SNAPSHOT` cleanup block. |
| 17 | create-context/install.sh copies snapshot to .claude/create-context/references/ with stale cleanup | VERIFIED | Lines 114-128: `mkdir -p "${TARGET_DIR}/create-context/references"`, copy, `STALE_SNAPSHOT` cleanup block. |
| 18 | gsd-patches/post-install.md is self-contained with stale cleanup, patch logic, and status markers | VERIFIED | 233 lines. Step 0 removes stale `apply-gsd-patches.md` and `.claude/gsd-patches/`. Patch discovery, anchor/replace parsing, AskUserQuestion conflict resolution. 4 status markers. No shell placeholders. |
| 19 | gsd-patches/install.sh is deleted | VERIFIED | `test ! -f gsd-patches/install.sh` — file absent. scan-status still finds gsd-patches via tool.toml-only discovery. |
| 20 | install.md Step 6 runs per-tool sequential with stop-on-error and three patterns | VERIFIED | Line 324: "execute the install in sequence. Stop immediately if any tool fails." Patterns A (copy-only), B (copy+configure), C (execute-only) all present. |
| 21 | install.md spawns Agent with post-install.md content and checks POST-INSTALL marker | VERIFIED | Lines 349-362: Agent invocation with prompt prefix, `POST-INSTALL: SUCCESS`/`FAILED` parsing, stop-on-error for missing marker. |
| 22 | Phase 8 requirement IDs recorded in REQUIREMENTS.md | FAILED | REQUIREMENTS.md ends at Phase 7. 22 Phase 8 IDs are in ROADMAP.md and PLAN frontmatter but absent from REQUIREMENTS.md. |

**Score:** 21/22 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `install/scripts/mg-install-lib.py` | Updated library: toml-only discovery, post_install/detect fields, checksums, adopt detect paths, scan-status pattern metadata | VERIFIED | 977 lines. All 7 targeted changes confirmed present. |
| `install/scripts/tests/test_mg_install_lib.py` | Extended test suite: 8 new tests covering all new behaviors | VERIFIED | 1698 lines. All 8 new test functions confirmed. 55 tests pass. |
| `install/TEMPLATE-post-install.md` | Template with POST-INSTALL status marker pattern | VERIFIED | Exists. Contains SUCCESS and FAILED markers in completion section. |
| `permission-hooks/post-install.md` | Self-contained subagent for hook install + settings.json registration | VERIFIED | 244 lines. No placeholders. Status markers. Hook logic intact. |
| `cc-regression-test/post-install.md` | Self-contained subagent for settings.json merge | VERIFIED | 114 lines. No placeholders. Status markers. Idempotent merge logic. |
| `gsd-patches/post-install.md` | Complete patch application logic as subagent (>=100 lines) | VERIFIED | 233 lines. Stale cleanup, patch discovery, anchor/replace, conflict resolution. |
| `gsd-patches/install.sh` | Deleted (execute-only tool) | VERIFIED | File absent from disk. Tool still discovered via tool.toml. |
| `install/commands/install.md` | Rewritten with three patterns, sequential execution, subagent orchestration (>=400 lines) | VERIFIED | 494 lines. All three patterns present. Agent invocation documented. |
| `permission-hooks/install.sh` | No command copy, empty COMMANDS array, stale cleanup | VERIFIED | `COMMANDS=()`. Stale cleanup block for `install-permission-hooks.md`. |
| `cc-regression-test/install.sh` | No inline Python, manifest update preserved | VERIFIED | No PYEOF. `update-manifest` call at line 154. |
| `mg-gsd-wrappers/install.sh` | Snapshot to references/, stale cleanup | VERIFIED | Copy to `mg-gsd-wrappers/references/`. Stale cleanup block. |
| `create-context/install.sh` | Snapshot to references/, stale cleanup | VERIFIED | Copy to `create-context/references/`. Stale cleanup block. |
| `.planning/REQUIREMENTS.md` | Phase 8 requirement IDs added | MISSING | File ends at Phase 7. No Phase 8 section, no traceability rows for 22 Phase 8 IDs. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `install/scripts/mg-install-lib.py` | `*/tool.toml` | `read_tool_toml` parsing `[post_install]` and `[detect]` sections | WIRED | `post_install_section` and `detect_section` present at lines 175-176. |
| `install/commands/install.md` | `*/post-install.md` | Agent tool reads post-install.md from source and spawns subagent | WIRED | Agent invocation documented at lines 349-362 with prompt prefix pattern. |
| `install/commands/install.md` | `install/scripts/mg-install-lib.py` | scan-status output includes `post_install` and `has_install_sh` fields | WIRED | Lines 326, 328, 336, 363: references `post_install` and `has_install_sh` from scan-status. |
| `permission-hooks/post-install.md` | target `settings.json` | subagent Python script for hook entry registration | WIRED | `permission-guard.py` hook copy and settings.json `PreToolUse` registration present. |
| `cc-regression-test/post-install.md` | target `settings.json` | subagent Python script for hook entry merge | WIRED | `intercept-trigger.py` hook command and `PreToolUse` merge logic present. |
| `gsd-patches/post-install.md` | `gsd-patches/patches/*.md` | reads patch templates from source directory | WIRED | Step 2 reads from `<source directory>/gsd-patches/patches/`. Anchor/replace logic present. |

---

## Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|---------|
| LIB-DISCOVER | 08-01 | SATISFIED | `discover_tools()` requires only tool.toml (line 204). |
| LIB-TOML | 08-01 | SATISFIED | `read_tool_toml()` returns `post_install_script` and `detect_paths`. |
| LIB-CHECKSUMS | 08-01 | SATISFIED | `patches/**/*.md` in CHECKSUM_INCLUDE; `post-install.md` in root file loop. |
| LIB-ADOPT | 08-01 | SATISFIED | Dual detection in `adopt_tools()`: commands OR detect paths. |
| LIB-SCANSTATUS | 08-01 | SATISFIED | `has_install_sh` and `post_install` in scan-status output. |
| TEMPLATE | 08-02 | SATISFIED | `install/TEMPLATE-post-install.md` with mandated status markers exists. |
| DETECT | 08-02 | SATISFIED | 9 tools have `[detect]` sections (6 mechanical + 3 with tier changes). |
| TIERS | 08-02 | SATISFIED | permission-hooks, gsd-patches, mg-gsd-wrappers set `standard=false`; cc-regression-test keeps `exclude=true`. |
| POSTINSTALL-PERMHOOKS | 08-03 | SATISFIED | `permission-hooks/post-install.md` self-contained, no placeholders, status markers. |
| POSTINSTALL-CCREGTEST | 08-03 | SATISFIED | `cc-regression-test/post-install.md` settings.json merge, idempotent, status markers. |
| POSTINSTALL-GSDPATCHES | 08-04 | SATISFIED | `gsd-patches/post-install.md` complete patch application, 233 lines, status markers. |
| EXECUTEONLY | 08-04 | SATISFIED | gsd-patches has no install.sh, only tool.toml + post-install.md. Still discovered. |
| SNAPSHOT-MGWRAPPERS | 08-03 | SATISFIED | mg-gsd-wrappers snapshot copied to `.claude/mg-gsd-wrappers/references/`. |
| SNAPSHOT-CREATECTX | 08-03 | SATISFIED | create-context snapshot copied to `.claude/create-context/references/`. |
| STALE-CLEANUP | 08-03 | SATISFIED | Stale cleanup in permission-hooks, mg-gsd-wrappers, create-context install.sh; gsd-patches post-install.md Step 0. |
| INSTALL-SEQUENTIAL | 08-05 | SATISFIED | Step 6: "execute the install in sequence." |
| INSTALL-STOPONERROR | 08-05 | SATISFIED | Step 6: "Stop immediately if any tool fails." |
| INSTALL-SUBAGENT | 08-05 | SATISFIED | Step 6 Pattern B and C: Agent invocation with prompt prefix. |
| INSTALL-STATUSMARKER | 08-05 | SATISFIED | Step 6: `POST-INSTALL: SUCCESS`/`FAILED` parsing with stop-on-error for missing marker. |
| INSTALL-EXECUTEONLY | 08-05 | SATISFIED | Pattern C calls `update-manifest` directly after post-install (no install.sh). |
| INSTALL-ADOPT | 08-05 | SATISFIED | Step 2b mentions `[detect]` paths in adopt detection. |
| INSTALL-TIERS | 08-05 | SATISFIED | Status table shows gsd-patches as optional; Key Constraint #5 excludes only install and cc-regression-test. |

**ORPHANED requirements (in ROADMAP.md but absent from REQUIREMENTS.md):** All 22 Phase 8 IDs listed above. They exist in PLAN frontmatter and are satisfied by the implementation, but REQUIREMENTS.md was never updated to include them.

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `permission-hooks/post-install.md` line 54 | `{PROJECT_ROOT}` appears in instructional text | Info | Intentional — this is text telling the subagent what sed replacement to perform, not an unresolved placeholder in a deployed file. No impact. |

No blocking or warning-level anti-patterns found across any modified files.

---

## Human Verification Required

### 1. Two-stage install end-to-end on a real project

**Test:** Run `/mg:install` on a test project, select permission-hooks, and let it complete both stages.
**Expected:** install.sh runs (copies hook file), then Agent subagent executes post-install.md and registers the PreToolUse hook entry in `.claude/settings.json`. Final output contains `POST-INSTALL: SUCCESS`.
**Why human:** Requires actual Agent subagent invocation through the Claude Code interface — cannot verify the full orchestration loop programmatically.

### 2. gsd-patches execute-only install on a project with GSD

**Test:** Run `/mg:install` on a project that has GSD installed, select gsd-patches.
**Expected:** No install.sh runs. Agent subagent executes post-install.md, reads patches from source, applies them to GSD workflow files. Final output contains `POST-INSTALL: SUCCESS`.
**Why human:** Requires real GSD installation in target and Agent subagent execution.

### 3. Stop-on-error behavior

**Test:** Simulate a post-install failure (e.g., point install.md at a target with missing settings.json write permissions).
**Expected:** install.md stops after the failed tool, shows full Agent output, reports remaining tools as "Not attempted".
**Why human:** Requires controlled failure conditions in Claude Code agent context.

---

## Gaps Summary

One gap found: the Phase 8 requirement IDs were never added to REQUIREMENTS.md. All 22 requirement IDs (LIB-DISCOVER through INSTALL-TIERS) are referenced in ROADMAP.md phase details and in the `requirements:` frontmatter of the 5 PLAN files, but REQUIREMENTS.md was last updated 2026-03-15 (Phase 1 creation) and covers only phases 1-7.

This is a documentation/traceability gap, not an implementation gap. Every requirement is fully satisfied in the codebase — the gap is that the traceability record is incomplete.

The implementation itself is complete: all 5 plans executed, all artifacts created, all key links wired, all 55 tests pass, and the full two-stage install model works end-to-end as designed.

---

_Verified: 2026-03-19T19:00:00Z_
_Verifier: Claude (gsd-verifier)_
