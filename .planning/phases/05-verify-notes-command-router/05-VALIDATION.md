---
phase: 5
slug: verify-notes-command-router
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | pyproject.toml (project root) |
| **Quick run command** | `python3 -m pytest create-docs/scripts/tests/ -x -q` |
| **Full suite command** | `python3 -m pytest -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest create-docs/scripts/tests/ -x -q`
- **After every plan wave:** Run `python3 -m pytest -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | CMD-04 | manual | End-to-end road-runner validation | N/A | ⬜ pending |
| 05-01-02 | 01 | 1 | VFY-01 | unit | `python3 -m pytest create-docs/scripts/tests/test_check_references.py -x` | ✅ | ⬜ pending |
| 05-01-03 | 01 | 1 | VFY-02 | manual | Agent-level LLM judgment | N/A | ⬜ pending |
| 05-01-04 | 01 | 1 | VFY-03 | manual | Agent-level LLM judgment | N/A | ⬜ pending |
| 05-01-05 | 01 | 1 | VFY-04 | manual | Agent-level LLM judgment | N/A | ⬜ pending |
| 05-01-06 | 01 | 1 | VFY-05 | manual | Agent-level LLM judgment | N/A | ⬜ pending |
| 05-01-07 | 01 | 1 | VFY-06 | manual | Agent-level LLM judgment | N/A | ⬜ pending |
| 05-01-08 | 01 | 1 | VFY-07 | manual | End-to-end road-runner validation | N/A | ⬜ pending |
| 05-02-01 | 02 | 1 | CMD-05 | unit | `python3 -m pytest create-docs/scripts/tests/test_add_note.py create-docs/scripts/tests/test_classify_note.py -x` | ✅ | ⬜ pending |
| 05-02-02 | 02 | 1 | CMD-01 | manual | End-to-end road-runner validation | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

- check-references.py: 8 tests passing (VFY-01 reference extraction)
- add-note.py: 8 tests passing (CMD-05 note append)
- classify-note.py: 11 tests passing (CMD-05 classification)
- All 59 tests green across 5 test files

No new test stubs or framework installation needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cross-doc consistency | VFY-02 | LLM judgment task — agent checks glossary terms against doc content | Run `/mg:create-docs-verify` on road-runner, check report for glossary inconsistency flags |
| Diataxis mixing detection | VFY-03 | LLM judgment task — agent evaluates content type vs declared type | Run verify on road-runner, check report for diataxis mixing warnings |
| Completeness audit | VFY-04 | LLM judgment task — agent compares scan data against docs | Run verify on road-runner, check report for coverage gaps |
| Example validity | VFY-05 | LLM judgment task — agent checks code block syntax | Run verify on road-runner, check report for example syntax issues |
| Link integrity | VFY-06 | LLM judgment task — agent resolves internal markdown links | Run verify on road-runner, check report for broken link flags |
| Verify report format | VFY-07 | Output format validation — need to inspect generated report | Verify docs-verify-report.md has severity categories, issue counts, structured sections |
| Router state detection | CMD-01 | LLM command behavior — depends on project filesystem state | Test on road-runner: fresh state, post-scan, post-generate, post-verify |
| Full pipeline E2E | SC-4 | Integration test — requires real project with source code | Run complete scan-generate-verify pipeline on road-runner |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
