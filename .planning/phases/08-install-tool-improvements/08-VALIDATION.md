---
phase: 08
slug: install-tool-improvements
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via .venv/bin/python) |
| **Config file** | pyproject.toml (implicit) |
| **Quick run command** | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py -x` |
| **Full suite command** | `.venv/bin/python -m pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py -x`
- **After every plan wave:** Run `.venv/bin/python -m pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | discover_tools() toml-only | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus::test_discovers_tools_with_toml_only -x` | Wave 0 (update) | ⬜ pending |
| 08-01-02 | 01 | 1 | read_tool_toml() post_install+detect | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus::test_reads_post_install_and_detect -x` | Wave 0 | ⬜ pending |
| 08-01-03 | 01 | 1 | scan-status install pattern fields | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus::test_scan_status_includes_install_pattern -x` | Wave 0 | ⬜ pending |
| 08-01-04 | 01 | 1 | checksums include post-install.md | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestUpdateManifest::test_checksums_include_post_install -x` | Wave 0 | ⬜ pending |
| 08-01-05 | 01 | 1 | checksums include patches/**/*.md | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestUpdateManifest::test_checksums_include_patches -x` | Wave 0 | ⬜ pending |
| 08-01-06 | 01 | 1 | adopt via detect paths | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestAdopt::test_detects_by_detect_paths -x` | Wave 0 | ⬜ pending |
| 08-01-07 | 01 | 1 | adopt skips execute-only | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestAdopt::test_skips_execute_only_tools -x` | Wave 0 | ⬜ pending |
| 08-01-08 | 01 | 1 | corrupt guard empty commands | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus::test_no_corrupt_for_empty_commands -x` | Wave 0 | ⬜ pending |
| 08-01-09 | 01 | 1 | regression | regression | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py -x` | ✅ existing (48 tests) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Update `_make_tool()` helper — add `has_install_sh`, `post_install_script`, `detect_paths` parameters
- [ ] `test_discovers_tools_with_toml_only` — update existing test that asserts tool.toml-only is NOT discovered
- [ ] `test_reads_post_install_and_detect` — new test for extended read_tool_toml()
- [ ] `test_scan_status_includes_install_pattern` — new test for post_install/has_install_sh fields
- [ ] `test_checksums_include_post_install` — new test for post-install.md in checksums
- [ ] `test_checksums_include_patches` — new test for patches/**/*.md in checksums
- [ ] `test_detects_by_detect_paths` — new test for adopt via detect paths
- [ ] `test_skips_execute_only_tools` — new test for adopt skipping execute-only
- [ ] `test_no_corrupt_for_empty_commands` — new test for corrupt guard

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Post-install.md subagent execution | Two-stage install | Requires Claude Code Agent tool runtime | Run `/mg:install` on road-runner, select permission-hooks, verify post-install.md subagent fires |
| install.md stop-on-error | Error handling | Requires Agent tool failure simulation | Run install with a tool that has a broken post-install.md, verify it stops |
| Status marker detection | POST-INSTALL: SUCCESS/FAILED | Requires Agent return text parsing | Run install, verify install.md correctly parses subagent output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
