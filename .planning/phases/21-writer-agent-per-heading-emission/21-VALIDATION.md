---
phase: 21
slug: writer-agent-per-heading-emission
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Full suite command** | `uv run python -m pytest --tb=short -q --no-header` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **After every plan wave:** Run `uv run python -m pytest --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | WHE-01 | integration | `uv run python -m pytest auto-doc/scripts/tests/ -k "write_section" --tb=short -q` | ✅ | ⬜ pending |
| 21-01-02 | 01 | 1 | WHE-04 | integration | `uv run python -m pytest auto-doc/scripts/tests/ -k "write_section" --tb=short -q` | ✅ | ⬜ pending |
| 21-01-03 | 01 | 1 | WHE-05 | integration | `uv run python -m pytest auto-doc/scripts/tests/ -k "write_section" --tb=short -q` | ✅ | ⬜ pending |
| 21-02-01 | 02 | 1 | WHE-01, WHE-02 | manual | See Manual-Only Verifications | N/A | ⬜ pending |
| 21-02-02 | 02 | 1 | WHE-03 | manual | See Manual-Only Verifications | N/A | ⬜ pending |
| 21-02-03 | 02 | 1 | WHE-06 | manual | See Manual-Only Verifications | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. write-section.py already has 51 tests covering `--parent` flag, nested finalize, merge mode, and recursive manifest/sections. No new test stubs needed — existing test coverage validates the infrastructure; new tests validate end-to-end agent prompt behavior.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Writer agents emit per-heading sections | WHE-01 | Agent prompt behavior — requires running writer on actual project | Run devops-writer on road-runner, inspect XML output for nested sections |
| Only 3 writers updated | WHE-02 | File diff check | Verify only devops-writer.md, glossary-writer.md, overview-writer.md modified |
| Markdown output unchanged | WHE-03 | Requires comparing generated docs before/after | Run generate on road-runner before and after, diff markdown output |
| Section markers at every heading level | WHE-04 | Inspect generated markdown | Grep for `<!-- section:` in generated docs, verify at ##/###/#### levels |
| Refs match body exactly | WHE-05 | Requires running verify-xml-refs on generated XML | Run verify-xml-refs.py on road-runner XML, expect zero misplaced refs |
| E2E round-trip fidelity | WHE-06 | Full pipeline test | Run scan→generate→verify→audit on road-runner, check convergence |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
