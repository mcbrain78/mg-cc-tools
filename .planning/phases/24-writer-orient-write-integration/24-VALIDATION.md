---
phase: 24
slug: writer-orient-write-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Full suite command** | `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **After every plan wave:** Run `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 24-01-01 | 01 | 1 | OWI-02, OWI-03 | unit | `uv run python -m pytest auto-doc/scripts/tests/test_generate_setup.py --tb=short -q --no-header` | ❌ W0 | ⬜ pending |
| 24-01-02 | 01 | 1 | OWI-01, OWI-04, OWI-05, OWI-07 | manual | Road-runner smoke test | N/A | ⬜ pending |
| 24-02-01 | 02 | 2 | OWI-06 | manual | Side-by-side comparison | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `auto-doc/scripts/tests/test_generate_setup.py` — extend with refined template detection tests for OWI-02, OWI-03

*Existing infrastructure covers most phase requirements. generate-setup.py extension is the only new testable Python logic.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Orient-write loop sequence | OWI-01 | Agent behavior requires LLM execution | Run devops-writer on road-runner, verify next-heading.py call sequence: orient → write × N → orient → write × N → done |
| Template coverage | OWI-04 | Agent behavior requires LLM execution | Compare emitted headings against refined template heading tree — all present, none extra |
| Refined-only input | OWI-05 | Agent prompt design, not runtime logic | Inspect devops-writer prompt — references refined template only, no generic template path |
| Content quality | OWI-06 | Subjective assessment | Side-by-side comparison of devops doc sections: new pipeline vs backup |
| Other writers unchanged | OWI-07 | Diff-based verification | `git diff` on non-devops writer files should be empty |
| Stale template warning | OWI-03 | Pipeline state-dependent | Re-scan without re-running prepare-templates, run generate — check for stale warning in output |
| Fallback to generic | OWI-02 | Pipeline state-dependent | Remove refined templates, run generate — should use generic templates without errors |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
