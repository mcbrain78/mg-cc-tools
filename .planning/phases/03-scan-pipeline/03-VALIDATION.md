---
phase: 3
slug: scan-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | pyproject.toml |
| **Quick run command** | `python3 -m pytest create-docs/scripts/tests/ -x -q` |
| **Full suite command** | `python3 -m pytest -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest create-docs/scripts/tests/ -x -q`
- **After every plan wave:** Run `python3 -m pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-xx | 01 | 1 | SCN-01 | manual-only | N/A — LLM analysis | N/A | ⬜ pending |
| 03-01-xx | 01 | 1 | SCN-02 | manual-only | N/A — LLM analysis | N/A | ⬜ pending |
| 03-01-xx | 01 | 1 | SCN-03 | manual-only | N/A — LLM reads .planning/ | N/A | ⬜ pending |
| 03-01-xx | 01 | 1 | SCN-04 | unit | `python3 -m pytest create-docs/scripts/tests/test_check_references.py -x` | ✅ (16 tests) | ⬜ pending |
| 03-01-xx | 01 | 1 | SCN-05 | unit | `python3 -m pytest create-docs/scripts/tests/test_staleness_check.py -x` | ✅ (14 tests) | ⬜ pending |
| 03-01-xx | 01 | 1 | SCN-06 | unit | `python3 -m pytest create-docs/scripts/tests/test_classify_note.py -x` | ✅ (11 tests) | ⬜ pending |
| 03-01-xx | 01 | 1 | SCN-07 | manual-only | N/A — LLM analysis | N/A | ⬜ pending |
| 03-01-xx | 01 | 1 | SCN-08 | unit | `python3 -m pytest create-docs/scripts/tests/test_merge_scan.py -x` | ✅ (10 tests) | ⬜ pending |
| 03-xx-xx | xx | x | CMD-02 | smoke | Run `/mg:create-docs-scan` on road-runner project | No — manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

All Python scripts (check-references.py, staleness-check.py, classify-note.py, merge-scan.py) were built in Phase 1 with 59 passing tests. No new test infrastructure needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Project orientation populates project_model | SCN-01 | LLM analysis of project structure — not scriptable | Run `/mg:create-docs-scan` on road-runner; verify `project_model` has tech_stack, components, entry_points |
| Source material index maps code to doc sections | SCN-02 | LLM maps files to documents — not scriptable | Verify `source_material_index` keys match `{DOCUMENT}/{section}` format, sources are real files |
| GSD context loads planning data | SCN-03 | LLM reads .planning/ directory — not scriptable | Run on a GSD project; verify `gsd_context` is populated with phase summaries and requirements |
| Gap analysis identifies undocumented components | SCN-07 | LLM identifies coverage gaps — not scriptable | Verify `gap_analysis.undocumented_components` lists real unscanned files |
| End-to-end scan command | CMD-02 | Full integration of LLM orchestration | Run `/mg:create-docs-scan` on road-runner; verify `docs-scan.json` is valid and complete |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
