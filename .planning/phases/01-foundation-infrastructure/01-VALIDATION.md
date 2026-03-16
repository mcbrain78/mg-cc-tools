---
phase: 1
slug: foundation-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` (implicit discovery, no explicit pytest config) |
| **Quick run command** | `python3 -m pytest create-docs/scripts/tests/ -x` |
| **Full suite command** | `python3 -m pytest -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest create-docs/scripts/tests/ -x`
- **After every plan wave:** Run `python3 -m pytest -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | INF-01 | unit + integration | `python3 -m pytest create-docs/scripts/tests/test_add_note.py -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | INF-02 | unit | `python3 -m pytest create-docs/scripts/tests/test_classify_note.py -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | INF-03 | unit + integration | `python3 -m pytest create-docs/scripts/tests/test_check_references.py -x` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | INF-04 | unit + integration | `python3 -m pytest create-docs/scripts/tests/test_merge_scan.py -x` | ❌ W0 | ⬜ pending |
| 01-01-05 | 01 | 1 | INF-05 | unit + integration | `python3 -m pytest create-docs/scripts/tests/test_staleness_check.py -x` | ❌ W0 | ⬜ pending |
| 01-01-06 | 01 | 1 | INF-06 | manual-only | Review `references/schema.md` against CONTEXT.md field list | N/A | ⬜ pending |
| 01-01-07 | 01 | 1 | INF-07 | manual-only | Review `references/style-guide.md` for completeness | N/A | ⬜ pending |
| 01-02-01 | 02 | 1 | INF-08 | integration | `bash create-docs/install.sh --project /tmp/test-install && ls -R /tmp/test-install/.claude/` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | INF-09 | integration | Tested as part of INF-08 install.sh --project test | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | INF-10 | unit | `python3 -m pytest create-docs/scripts/tests/test_config.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `create-docs/scripts/tests/__init__.py` — empty package marker
- [ ] `create-docs/scripts/tests/test_add_note.py` — stubs for INF-01
- [ ] `create-docs/scripts/tests/test_classify_note.py` — stubs for INF-02
- [ ] `create-docs/scripts/tests/test_check_references.py` — stubs for INF-03
- [ ] `create-docs/scripts/tests/test_merge_scan.py` — stubs for INF-04
- [ ] `create-docs/scripts/tests/test_staleness_check.py` — stubs for INF-05
- [ ] `create-docs/scripts/tests/test_config.py` — stubs for INF-10

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Schema defines all docs-scan.json fields | INF-06 | Content completeness requires human review against CONTEXT.md field list | Review `references/schema.md` — verify all fields from CONTEXT.md are documented with types and examples |
| Style guide contains cross-audience conventions | INF-07 | Writing quality and coverage requires human judgment | Review `references/style-guide.md` — verify conventions for all 4 audiences, Diataxis alignment, and concrete examples |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
