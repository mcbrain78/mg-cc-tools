---
phase: 7
slug: install-command
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-17
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (via python3 -m pytest) |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `python3 -m pytest install/scripts/tests/ -x` |
| **Full suite command** | `python3 -m pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest install/scripts/tests/ -x`
- **After every plan wave:** Run `python3 -m pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | INST-01 | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | INST-02 | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestToolMetadata -x` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 1 | INST-03 | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestStaleness -x` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 1 | INST-04 | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestManifest -x` | ❌ W0 | ⬜ pending |
| 07-01-05 | 01 | 1 | INST-05 | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestPreflight -x` | ❌ W0 | ⬜ pending |
| 07-01-06 | 01 | 1 | INST-07 | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestAdopt -x` | ❌ W0 | ⬜ pending |
| 07-01-07 | 01 | 1 | INST-08 | unit | `python3 -m pytest install/scripts/tests/test_mg_install_lib.py::TestValidate -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | INST-02 | smoke | `test -f <tool>/tool.toml` per tool | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | INST-09 | manual-only | N/A (interactive LLM prompt) | N/A | ⬜ pending |
| 07-04-01 | 04 | 2 | INST-10 | integration | Run modified install.sh on temp dir, check manifest | ❌ W0 | ⬜ pending |
| 07-04-02 | 04 | 2 | INST-11 | smoke | `install/install.sh --target <tmp>` verify install.md copied | ❌ W0 | ⬜ pending |
| 07-05-01 | 05 | 3 | INST-06 | manual-only | N/A (requires claude -p runtime) | N/A | ⬜ pending |
| 07-05-02 | 05 | 3 | INST-09 | manual-only | N/A (road-runner end-to-end validation) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `install/scripts/tests/test_mg_install_lib.py` — stubs for INST-01 through INST-08, INST-12
- [ ] `install/scripts/tests/__init__.py` — package marker (if needed by test runner)
- [ ] Framework install: N/A — pytest already in pyproject.toml dev dependencies

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LSP capability probe | INST-06 | Requires `claude -p` runtime and project-specific LSP configuration | Run `/mg:install` on road-runner, verify capabilities section in manifest shows lsp field |
| install.md interactive flow | INST-09 | Interactive LLM prompt with AskUserQuestion and numbered prompts | Run `/mg:install` on road-runner: 1) target selection, 2) status table, 3) action selection, 4) install, 5) summary |
| Road-runner migration | INST-07 | Road-runner has pre-manifest installs that test adopt flow | Run `/mg:install` on road-runner (first time), verify it detects existing tools and offers adopt |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
