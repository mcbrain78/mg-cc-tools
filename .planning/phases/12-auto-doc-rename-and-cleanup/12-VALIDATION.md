---
phase: 12
slug: auto-doc-rename-and-cleanup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0+ |
| **Config file** | pyproject.toml (project root) |
| **Quick run command** | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Full suite command** | `python3 -m pytest --tb=short -q --no-header` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **After every plan wave:** Run `python3 -m pytest --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | Rename create-docs to auto-doc | regression | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` | Exists (moves with rename) | ⬜ pending |
| 12-01-02 | 01 | 1 | Migration path in install.sh | smoke | Manual: install in test project, verify old files removed | N/A | ⬜ pending |
| 12-01-03 | 01 | 1 | Cross-tool reference updates | smoke | Manual grep for stale refs | N/A | ⬜ pending |
| 12-02-01 | 02 | 2 | staleness-check.py dict wrapper | unit | `python3 -m pytest auto-doc/scripts/tests/test_staleness_check.py::TestCLI::test_cli_json_output -x` | Exists (needs update) | ⬜ pending |
| 12-02-02 | 02 | 2 | staleness-check.py --output dict | unit | `python3 -m pytest auto-doc/scripts/tests/test_staleness_check.py::TestCLI::test_cli_output_file -x` | Exists (needs update) | ⬜ pending |
| 12-02-03 | 02 | 2 | add-note.py note_id field | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_note.py -x` | Exists (needs update) | ⬜ pending |
| 12-02-04 | 02 | 2 | add-note.py JSON stdout | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_note.py::TestAddNoteBasic::test_append_to_empty_inbox -x` | Exists (needs new assertion) | ⬜ pending |
| 12-02-05 | 02 | 2 | classify-note.py note_id | unit | `python3 -m pytest auto-doc/scripts/tests/test_classify_note.py -x` | Exists (needs update) | ⬜ pending |
| 12-02-06 | 02 | 2 | Remove dead check-references.py call | smoke | Scan pipeline produces valid docs-scan.json | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Add test assertion for `add-note.py` JSON stdout output (new behavior in 12-02-04)
- [ ] Add scan pipeline smoke test to verify `docs-scan.json` production after `check-references.py` call removal (12-02-06)

*Existing infrastructure covers all other phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| No `create-docs`/`add-docs` refs outside exclusions | Rename completeness | Repo-wide grep not suited for unit test | `grep -rn "create-docs\|add-docs" --include="*.py" --include="*.md" --include="*.sh" . \| grep -v ".planning/" \| grep -v "docs/work-queue/"` |
| Migration removes old files in target project | Install migration | Requires real install target | Run `install.sh --project /tmp/test-project`, verify `.claude/commands/mg/create-docs*.md` absent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
