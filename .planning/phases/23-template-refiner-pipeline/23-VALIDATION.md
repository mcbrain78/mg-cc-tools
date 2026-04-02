---
phase: 23
slug: template-refiner-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 23 — Validation Strategy

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
| TBD | TBD | TBD | TRF-01 | manual | Install + run command on test project | N/A | ⬜ pending |
| TBD | TBD | TBD | TRF-02 | manual | Verify refined template headings from scan data | N/A | ⬜ pending |
| TBD | TBD | TBD | TRF-03 | manual | Inspect PURPOSE comments for project-specific facts | N/A | ⬜ pending |
| TBD | TBD | TBD | TRF-04 | manual | Inspect EXAMPLE blocks for generic-only content | N/A | ⬜ pending |
| TBD | TBD | TBD | TRF-05 | manual | Compare refined template ## slugs against generic template | N/A | ⬜ pending |
| TBD | TBD | TBD | TRF-06 | manual | Verify writer receives refined template, not generic | N/A | ⬜ pending |
| TBD | TBD | TBD | TRF-07 | manual | Run prepare-templates twice, diff outputs | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. This phase creates markdown command/agent files — no new Python scripts requiring unit tests.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Command produces refined templates | TRF-01 | LLM orchestration output | Run `/mg:auto-doc-prepare-templates` on a scanned project, verify `.mg/docs/templates/` populated |
| Refiner explores source and adds headings | TRF-02 | LLM judgment call | Inspect refined template for appropriate `###`/`####` headings |
| PURPOSE comments are project-specific | TRF-03 | LLM content quality | Read PURPOSE comments, verify counts/names from source |
| EXAMPLE blocks are generic | TRF-04 | LLM content quality | Read EXAMPLE blocks, verify no project-specific values |
| ## slugs preserved from generic | TRF-05 | Structural check | Diff `##` headings between generic and refined template |
| Refined template replaces generic | TRF-06 | Pipeline integration | Verify writer prompt receives refined path when available |
| Idempotent output | TRF-07 | Determinism check | Run twice on same scan, diff refined templates |

*All requirements involve LLM-generated markdown content — automated unit testing is not applicable.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
