---
phase: 20
slug: recursive-pipeline-script-updates
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | pyproject.toml |
| **Quick run command** | `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header` |
| **Full suite command** | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header`
- **After every plan wave:** Run `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 1 | RPS-01 | unit | `python3 -m pytest auto-doc/scripts/tests/test_verify_xml_refs.py -x` | Needs update | ⬜ pending |
| 20-01-02 | 01 | 1 | RPS-02 | unit | `python3 -m pytest auto-doc/scripts/tests/test_verify_xml_refs.py -x` | Needs update | ⬜ pending |
| 20-01-03 | 01 | 1 | RPS-03 | unit | `python3 -m pytest auto-doc/scripts/tests/test_prepare_prose_verify.py -x` | Needs update | ⬜ pending |
| 20-02-01 | 02 | 1 | RPS-04 | unit | `python3 -m pytest auto-doc/scripts/tests/test_extract_edit_xml.py -x` | Needs update | ⬜ pending |
| 20-02-02 | 02 | 1 | RPS-05 | unit | `python3 -m pytest auto-doc/scripts/tests/test_merge_edit_xml.py -x` | Needs update | ⬜ pending |
| 20-03-01 | 03 | 2 | RPS-06 | unit | `python3 -m pytest auto-doc/scripts/tests/test_sync_edits.py -x` | Needs update | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. Tests need updating (not creating) to use nested fixtures.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
