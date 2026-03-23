---
phase: 17
slug: auto-doc-generate-docs-improvements
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-23
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py --tb=short -q --no-header` |
| **Full suite command** | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py --tb=short -q --no-header`
- **After every plan wave:** Run `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 1 | GEN-08 | unit | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py -k audience --tb=short -q --no-header` | ❌ W0 | ⬜ pending |
| 17-01-02 | 01 | 1 | GEN-09 | unit | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py -k glossary --tb=short -q --no-header` | ❌ W0 | ⬜ pending |
| 17-01-03 | 01 | 1 | GEN-11 | unit | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py -k structure --tb=short -q --no-header` | ❌ W0 | ⬜ pending |
| 17-01-04 | 01 | 1 | GEN-12 | unit | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py -k size --tb=short -q --no-header` | ❌ W0 | ⬜ pending |
| 17-02-01 | 02 | 2 | GEN-10 | manual-only | N/A — .md orchestrator changes | N/A | ⬜ pending |
| 17-02-02 | 02 | 2 | GEN-07 | manual-only | N/A — .md agent file changes | N/A | ⬜ pending |
| 17-02-03 | 02 | 2 | GEN-13 | existing | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py --tb=short -q --no-header` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `auto-doc/scripts/tests/test_split_scan_by_audience.py` — stubs for GEN-08, GEN-09, GEN-11, GEN-12
- No framework install needed — pytest already configured
- No conftest needed — existing test pattern uses standalone tempfile.TemporaryDirectory

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Writer agents contain Serena guidance principles | GEN-07 | .md prompt file changes, not executable code | Read each of the 5 writer agent .md files, verify "Source Code Exploration" principle present with correct tool usage instructions |
| Orchestrator routes view file paths to writers | GEN-10 | .md orchestrator changes, not executable code | Read auto-doc-generate.md, verify split-scan calls before writer spawning and view paths passed as scan_data_path |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
