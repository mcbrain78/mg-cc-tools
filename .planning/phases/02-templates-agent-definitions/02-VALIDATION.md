---
phase: 2
slug: templates-agent-definitions
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | pyproject.toml |
| **Quick run command** | `python3 -m pytest create-docs/scripts/tests/ -x` |
| **Full suite command** | `python3 -m pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Verify files exist and contain expected comment patterns
- **After every plan wave:** Run `python3 -m pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | TPL-01 | manual-only | Grep for PURPOSE and EXAMPLE comments in all templates | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | TPL-02 | smoke | `test -f create-docs/references/templates/OVERVIEW.template.md` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | TPL-03 | manual-only | Grep for `<!-- OPTIONAL` in templates | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | AGT-01 | manual-only | Read file, verify conventions present | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | AGT-02 | manual-only | Read file, verify conventions present | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 2 | AGT-03 | manual-only | Read file, verify conventions present | ❌ W0 | ⬜ pending |
| 02-02-04 | 02 | 2 | AGT-04 | manual-only | Read file, verify conventions present | ❌ W0 | ⬜ pending |
| 02-02-05 | 02 | 2 | AGT-05 | manual-only | Read file, verify reconciliation instructions | ❌ W0 | ⬜ pending |
| 02-02-06 | 02 | 2 | AGT-06 | manual-only | Read file, verify staleness-check.py integration | ❌ W0 | ⬜ pending |
| 02-02-07 | 02 | 2 | AGT-07 | manual-only | Read file, verify check-references.py integration | ❌ W0 | ⬜ pending |
| 02-02-08 | 02 | 2 | AGT-08 | manual-only | Verify execution order in TEMPLATE.md and agents | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] No new test files needed — Phase 2 deliverables are content files verified by reading
- [ ] install.sh patch needs existing test suite to still pass: `python3 -m pytest`
- [ ] File existence verification via bash: check all 13 templates and 8 agent files exist

*Existing infrastructure covers automated verification needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Three-layer template architecture | TPL-01 | Content quality requires reading | Check each template has Diataxis comment, structural headings with purpose, and exemplar per section |
| Optional section marking | TPL-03 | Semantic content inspection | Grep for `<!-- OPTIONAL -->` in templates that have optional sections |
| Writer agent format conventions | AGT-01–04 | Agent prompt quality is subjective | Read each writer agent, verify audience-specific conventions and Diataxis guidance |
| Glossary reconciliation | AGT-05 | Workflow validation | Read glossary agent, verify initial-pass and reconciliation instructions |
| Staleness scanner integration | AGT-06 | Integration path verification | Read agent, verify references to staleness-check.py |
| Verifier integration | AGT-07 | Integration path verification | Read agent, verify references to check-references.py |
| Parallel execution | AGT-08 | Orchestration design review | Verify execution order matches cross-cutting decisions |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
