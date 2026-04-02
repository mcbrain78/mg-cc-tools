---
phase: 22
slug: heading-iterator-script
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `pytest auto-doc/scripts/tests/test_next_heading.py --tb=short -q --no-header` |
| **Full suite command** | `pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest auto-doc/scripts/tests/test_next_heading.py --tb=short -q --no-header`
- **After every plan wave:** Run `pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | HIT-01 | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestCLI -x` | ❌ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | HIT-02 | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestTemplateParsing -x` | ❌ W0 | ⬜ pending |
| 22-01-03 | 01 | 1 | HIT-03 | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestOrientResponse -x` | ❌ W0 | ⬜ pending |
| 22-01-04 | 01 | 1 | HIT-04 | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestWriteResponse -x` | ❌ W0 | ⬜ pending |
| 22-01-05 | 01 | 1 | HIT-05 | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestDoneResponse -x` | ❌ W0 | ⬜ pending |
| 22-01-06 | 01 | 1 | HIT-06 | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestDepthFirstOrdering -x` | ❌ W0 | ⬜ pending |
| 22-01-07 | 01 | 1 | HIT-07 | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestHeadingPathConvention -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `auto-doc/scripts/tests/test_next_heading.py` — stubs for HIT-01 through HIT-07
- [ ] `auto-doc/scripts/next-heading.py` — the script itself

*Existing infrastructure covers all framework needs.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
