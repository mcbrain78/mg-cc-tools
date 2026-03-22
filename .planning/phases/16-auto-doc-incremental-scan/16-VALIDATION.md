---
phase: 16
slug: auto-doc-incremental-scan
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (dev dependency in pyproject.toml) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py -x --tb=short -q --no-header` |
| **Full suite command** | `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py -x --tb=short -q --no-header`
- **After every plan wave:** Run `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 1 | ISC-02 | unit | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py -x` | ❌ W0 | ⬜ pending |
| 16-01-02 | 01 | 1 | ISC-03 | unit | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py::TestRenameDetection -x` | ❌ W0 | ⬜ pending |
| 16-01-03 | 01 | 1 | ISC-05 | unit | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py::TestNewFileCandidates -x` | ❌ W0 | ⬜ pending |
| 16-01-04 | 01 | 1 | ISC-06 | unit | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py::TestGSDOptional -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `auto-doc/scripts/tests/test_diff_scan.py` — stubs for ISC-02, ISC-03, ISC-05, ISC-06
- No framework install needed (pytest already in dev dependencies)
- No conftest.py needed (existing test files are self-contained)

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mode detection (initial vs incremental) | ISC-01 | Requires full pipeline with docs/manifests/docs-scan.json present | Run `/mg:auto-doc-scan` with and without existing docs/manifests/last_generated |
| Scan agents receive scoped input + carry forward | ISC-04 | Requires LLM agent execution via Task tool | Run incremental scan and verify agent output includes both changed analysis and carried-forward entries |
| Diff-focused summary after incremental scan | ISC-07 | Requires LLM scan command execution | Run incremental scan and verify summary shows files changed/sections affected, not full project model |
| Verify runs unchanged in both modes | ISC-08 | No code changes needed — existing behavior | Run verify after incremental scan and confirm full verification runs |
| Full re-scan by deleting docs + docs-scan.json | ISC-09 | Requires pipeline state manipulation | Delete `docs/auto-doc/` and `.mg/docs/docs-scan.json`, run scan, verify initial mode triggers |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
