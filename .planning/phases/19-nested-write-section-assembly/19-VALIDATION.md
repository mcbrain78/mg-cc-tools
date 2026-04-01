---
phase: 19
slug: nested-write-section-assembly
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Full suite command** | `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **After every plan wave:** Run `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | WSA-01 | unit | `uv run python -m pytest auto-doc/scripts/tests/test_write_section.py -k parent --tb=short -q` | ❌ W0 | ⬜ pending |
| 19-01-02 | 01 | 1 | WSA-02 | unit | `uv run python -m pytest auto-doc/scripts/tests/test_write_section.py -k parent_exists --tb=short -q` | ❌ W0 | ⬜ pending |
| 19-01-03 | 01 | 1 | WSA-03 | unit | `uv run python -m pytest auto-doc/scripts/tests/test_write_section.py -k finalize --tb=short -q` | ❌ W0 | ⬜ pending |
| 19-01-04 | 01 | 1 | WSA-04 | unit | `uv run python -m pytest auto-doc/scripts/tests/test_write_section.py -k merge --tb=short -q` | ❌ W0 | ⬜ pending |
| 19-02-01 | 02 | 1 | WSA-05 | unit | `uv run python -m pytest auto-doc/scripts/tests/test_assemble_markdown.py -k recursive --tb=short -q` | ❌ W0 | ⬜ pending |
| 19-02-02 | 02 | 1 | WSA-06 | unit | `uv run python -m pytest auto-doc/scripts/tests/test_assemble_markdown.py -k flat_output --tb=short -q` | ❌ W0 | ⬜ pending |
| 19-02-03 | 02 | 1 | WSA-07 | unit | `uv run python -m pytest auto-doc/scripts/tests/test_write_section.py -k clean_cutover --tb=short -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `auto-doc/scripts/tests/test_write_section.py` — add test cases for --parent flag, nested state, finalize, merge mode, clean cutover (WSA-01 through WSA-04, WSA-07)
- [ ] `auto-doc/scripts/tests/test_assemble_markdown.py` — add test cases for recursive depth-first assembly, flat output verification (WSA-05, WSA-06)

*Existing test infrastructure covers framework and fixtures.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
