---
phase: 9
slug: session-analyzer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (from pyproject.toml dev deps) |
| **Config file** | None — Wave 0 creates conftest.py for --slow flag |
| **Quick run command** | `python3 -m pytest session-analyzer/tests/ -x -q` |
| **Full suite command** | `python3 -m pytest session-analyzer/tests/ --slow -x -q` |
| **Estimated runtime** | ~5 seconds (quick), ~30 seconds (full with 75MB sample) |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest session-analyzer/tests/ -x -q --tb=short`
- **After every plan wave:** Run `python3 -m pytest session-analyzer/tests/ --slow -x -q --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 0 | SAN-21 | unit | `python3 -m pytest session-analyzer/tests/ -x -q` | ❌ W0 | ⬜ pending |
| 09-02-01 | 02 | 1 | SAN-01 | unit | `python3 -m pytest session-analyzer/tests/test_compactor_rename.py -x` | ❌ W0 | ⬜ pending |
| 09-02-02 | 02 | 1 | SAN-02 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_overview.py::test_load_drops_chunks -x` | ❌ W0 | ⬜ pending |
| 09-02-03 | 02 | 1 | SAN-03 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_overview.py -x` | ❌ W0 | ⬜ pending |
| 09-02-04 | 02 | 1 | SAN-12 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_errors.py::TestErrorDetection -x` | ❌ W0 | ⬜ pending |
| 09-02-05 | 02 | 1 | SAN-13 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_errors.py::TestNoiseFiltering -x` | ❌ W0 | ⬜ pending |
| 09-02-06 | 02 | 1 | SAN-11 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_pagination.py -x` | ❌ W0 | ⬜ pending |
| 09-02-07 | 02 | 1 | SAN-14 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_flow.py::TestAgentLinkage -x` | ❌ W0 | ⬜ pending |
| 09-02-08 | 02 | 1 | SAN-15 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_msg.py::TestPersistedRecovery -x` | ❌ W0 | ⬜ pending |
| 09-02-09 | 02 | 1 | SAN-18 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_overview.py::test_no_ansi -x` | ❌ W0 | ⬜ pending |
| 09-03-01 | 03 | 1 | SAN-04 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_errors.py -x` | ❌ W0 | ⬜ pending |
| 09-03-02 | 03 | 1 | SAN-05 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_flow.py -x` | ❌ W0 | ⬜ pending |
| 09-03-03 | 03 | 1 | SAN-06 | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_agent.py -x` | ❌ W0 | ⬜ pending |
| 09-03-04 | 03 | 1 | SAN-07 | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_agent.py::TestAgentList -x` | ❌ W0 | ⬜ pending |
| 09-03-05 | 03 | 1 | SAN-08 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_msg.py -x` | ❌ W0 | ⬜ pending |
| 09-03-06 | 03 | 1 | SAN-09 | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_search.py -x` | ❌ W0 | ⬜ pending |
| 09-03-07 | 03 | 1 | SAN-10 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_export.py -x` | ❌ W0 | ⬜ pending |
| 09-03-08 | 03 | 1 | SAN-16 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_agent.py::TestAmbiguousPrefix -x` | ❌ W0 | ⬜ pending |
| 09-03-09 | 03 | 1 | SAN-17 | unit+slow | `python3 -m pytest session-analyzer/tests/test_analyzer_search.py::TestSearchScope -x` | ❌ W0 | ⬜ pending |
| 09-03-10 | 03 | 1 | SAN-23 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_overview.py::TestContextualCommands -x` | ❌ W0 | ⬜ pending |
| 09-03-11 | 03 | 1 | SAN-24 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_msg.py::TestDisplayModes -x` | ❌ W0 | ⬜ pending |
| 09-04-01 | 04 | 2 | SAN-19 | manual | Verify install.sh, tool.toml, command file exist and install correctly | N/A | ⬜ pending |
| 09-04-02 | 04 | 2 | SAN-20 | manual | Run command with and without goal argument | N/A | ⬜ pending |
| 09-04-03 | 04 | 2 | SAN-22 | unit | `python3 -m pytest session-analyzer/tests/test_analyzer_errors.py::TestIndependentDetection -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `session-analyzer/tests/__init__.py` — package marker
- [ ] `session-analyzer/tests/conftest.py` — `--slow` pytest flag, sample path fixtures, skip logic for missing samples
- [ ] All test stub files for Wave 1 plans
- [ ] pyproject.toml update: add `[tool.pytest.ini_options]` with `markers = ["slow: marks tests requiring large sample files"]`

*Note: Wave 0 is embedded in Plan 01 (test infrastructure setup).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Slash command installs correctly | SAN-19 | Requires install.sh execution in target project | Run `./session-analyzer/install.sh --project /tmp/test-target`, verify files copied |
| Dual mode command | SAN-20 | Requires Claude Code runtime for LLM-driven query loop | Run `/mg:analyze-session sample.json` and `/mg:analyze-session sample.json "why did the build fail?"` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
