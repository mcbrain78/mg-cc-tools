---
phase: 11
slug: add-tooling-to-install-command
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via `.venv/bin/pytest`) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py --tb=short -q --no-header` |
| **Full suite command** | `.venv/bin/pytest --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py --tb=short -q --no-header`
- **After every plan wave:** Run `.venv/bin/pytest --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | INST-53 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "determine_scenario" -x` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | INST-43 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "auto_adopt" -x` | ❌ W0 | ⬜ pending |
| 11-01-03 | 01 | 1 | INST-44, INST-51 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "render_action_menu" -x` | ❌ W0 | ⬜ pending |
| 11-01-04 | 01 | 1 | INST-45 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "resolve_action" -x` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 1 | INST-46, INST-56 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "install_plan" -x` | ❌ W0 | ⬜ pending |
| 11-02-02 | 02 | 1 | INST-47 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "render_preflight" -x` | ❌ W0 | ⬜ pending |
| 11-02-03 | 02 | 1 | INST-48 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "record_result" -x` | ❌ W0 | ⬜ pending |
| 11-02-04 | 02 | 1 | INST-49 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "render_summary" -x` | ❌ W0 | ⬜ pending |
| 11-02-05 | 02 | 1 | INST-50 | unit | `.venv/bin/pytest install/scripts/tests/test_mg_install_lib.py -k "render_validation" -x` | ❌ W0 | ⬜ pending |
| 11-03-01 | 03 | 2 | INST-52, INST-54 | manual | Manual: run `/mg:install` on test target | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `TestDetermineScenario` class — tests for _determine_scenario shared helper (3 scenarios + edge cases)
- [ ] `TestAutoAdopt` additions — tests for --auto-adopt flag on scan-status
- [ ] `TestRenderActionMenu` class — scenario A/B/C menu output tests with dynamic counts
- [ ] `TestResolveAction` class — menu option mapping + fallback to tool selection
- [ ] `TestGetInstallPlan` class — pattern determination, expected_action, --output support
- [ ] `TestRenderPreflight` class — PASS/FAIL formatting, required/optional grouping
- [ ] `TestRecordResult` class — file creation, append, success/failed entries
- [ ] `TestRenderSummary` class — action column, command filenames, capability merge
- [ ] `TestRenderValidation` class — PASS/WARNING formatting, issue details
- [ ] Fixture: extended `_make_scan_status_fixture()` variants for all 3 scenarios
- [ ] Fixture: `_make_preflight_fixture()` for preflight renderer tests
- [ ] Fixture: `_make_install_plan_fixture()` for record-result and render-summary tests
- [ ] `cmd_preflight` --output support tests (addition to existing `TestPreflight`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| install.md thin orchestrator | INST-52 | Requires Claude Code runtime + user interaction | Run `/mg:install` on road-runner, verify 8-step flow uses subcommand calls |
| Consolidated rendering rule | INST-54 | Prompt structure check | Inspect install.md for single rendering rule at top, no per-subcommand echo instructions |
| Stdlib-only | INST-57 | Import inspection | Verify no non-stdlib imports added to mg-install-lib.py |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
