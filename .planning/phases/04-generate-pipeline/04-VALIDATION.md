---
phase: 4
slug: generate-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python3 -m pytest create-context/scripts/tests/ -x -q` |
| **Full suite command** | `python3 -m pytest create-context/scripts/tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest create-context/scripts/tests/ -x -q`
- **After every plan wave:** Run `python3 -m pytest create-context/scripts/tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Initial mode generates 12 docs across 4 audience dirs | GEN-01, DOC-01–DOC-13 | Requires LLM-based generation; output quality is subjective | Run `/mg:create-docs-generate` on `../road-runner`, verify directory structure and section presence |
| Update mode staleness approval flow | GEN-02 | Interactive UX with AskUserQuestion | Run generate in update mode, verify staleness report appears and approval flow works |
| Notes integration expands into prose | GEN-03 | LLM output quality; requires human judgment | Add test note via inbox, run update, verify expansion and placement |
| OVERVIEW.md routes accurately to audience docs | DOC-01 | Cross-document consistency; requires reading comprehension | Check OVERVIEW.md links and descriptions match generated docs |
| Glossary reconciliation flags inconsistencies | GEN-05 | Cross-agent terminology consistency | Review glossary after generation, check proposed terms from writers are incorporated |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
