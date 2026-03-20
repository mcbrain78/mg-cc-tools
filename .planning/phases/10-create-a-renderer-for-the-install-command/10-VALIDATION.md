---
phase: 10
slug: create-a-renderer-for-the-install-command
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via `.venv/bin/activate`) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py --tb=short -q --no-header` |
| **Full suite command** | `source .venv/bin/activate && python3 -m pytest --tb=short -q --no-header` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py --tb=short -q --no-header`
- **After every plan wave:** Run `source .venv/bin/activate && python3 -m pytest --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | INST-35, INST-36, INST-37, INST-38, INST-42 | unit | `source .venv/bin/activate && python3 -m pytest install/scripts/tests/test_mg_install_lib.py -k "TestRenderStatusTable or TestRenderToolPicker or TestResolveToolSelection" -x` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 1 | INST-39, INST-40, INST-41 | manual-only | Review install.md source | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `TestRenderStatusTable` class in `test_mg_install_lib.py` — stubs for INST-35
- [ ] `TestRenderToolPicker` class in `test_mg_install_lib.py` — stubs for INST-36
- [ ] `TestResolveToolSelection` class in `test_mg_install_lib.py` — stubs for INST-37, INST-38

*Existing infrastructure covers framework and fixtures (55 tests passing). Only new test classes needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| install.md Step 2 calls render-status-table | INST-39 | LLM prompt, not executable code | Verify install.md replaces template with subcommand call |
| install.md Step 3 uses picker + resolver | INST-40 | LLM prompt, not executable code | Verify install.md adds render-tool-picker and resolve-tool-selection calls |
| Scenario menus remain LLM-rendered | INST-41 | LLM prompt, not executable code | Verify install.md still contains scenario A/B/C text menus |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
