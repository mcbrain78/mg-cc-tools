---
phase: 14
slug: auto-doc-reference-manifest
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` (existing) |
| **Quick run command** | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py -x --tb=short -q --no-header` |
| **Full suite command** | `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py -x --tb=short -q --no-header`
- **After every plan wave:** Run `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | MAN-01, MAN-03 | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py -x` | ❌ W0 | ⬜ pending |
| 14-01-02 | 01 | 1 | MAN-06 | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py::TestWrittenSections -x` | ❌ W0 | ⬜ pending |
| 14-01-03 | 01 | 1 | MAN-10 | unit | `python3 -m pytest auto-doc/scripts/tests/ -x` | ✅ | ⬜ pending |
| 14-02-01 | 02 | 2 | MAN-02 | manual-only | End-to-end pipeline run | N/A | ⬜ pending |
| 14-02-02 | 02 | 2 | MAN-04, MAN-05 | manual-only | End-to-end pipeline run | N/A | ⬜ pending |
| 14-02-03 | 02 | 2 | MAN-07, MAN-08, MAN-09, MAN-11 | manual-only | End-to-end pipeline run | N/A | ⬜ pending |
| 14-02-04 | 02 | 2 | MAN-12 | manual-only | End-to-end pipeline run | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `auto-doc/scripts/tests/test_add_manifest_entry.py` — stubs for MAN-01, MAN-03, MAN-06
- No conftest changes needed — existing test patterns are sufficient
- No framework install needed — pytest already in dev dependencies

*Existing infrastructure covers MAN-10 (deletion of test file verifiable via existing suite passing).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Writer agents emit manifest entries per section | MAN-02 | LLM prompt change in .md agent definitions | Run `/mg:auto-doc-generate` on target project, verify `/tmp/manifest-{audience}.json` files created |
| Generate orchestrator merges temp manifests | MAN-04, MAN-05 | LLM prompt change in generate command | Run generate in initial mode (verify manifests cleared first) and update mode (verify upsert only) |
| Verify reads manifests and checks via LSP | MAN-07, MAN-08, MAN-09, MAN-11 | LLM prompt change in verifier agent | Run `/mg:auto-doc-verify` on target project, verify report groups findings by doc+section |
| Manifest covers audience-specific only | MAN-12 | Design constraint, not code logic | Verify no manifest file for shared docs after generation |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
