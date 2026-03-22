---
phase: 15
slug: auto-doc-enduser-quality
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via `python3 -m pytest`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header` |
| **Full suite command** | `python3 -m pytest --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header`
- **After every plan wave:** Run `python3 -m pytest --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | EUQ-04, EUQ-10 | manual | Template structural validation (7 headings, comment types) | N/A | ⬜ pending |
| 15-01-02 | 01 | 1 | EUQ-06, EUQ-07 | manual | Schema field documentation review | N/A | ⬜ pending |
| 15-02-01 | 02 | 1 | EUQ-03, EUQ-06, EUQ-07 | manual | Agent instruction review (SYNTHESIZED/BOUNDARY/exclusion handling) | N/A | ⬜ pending |
| 15-02-02 | 02 | 1 | EUQ-01 | manual | Interface detection step review in scan command | N/A | ⬜ pending |
| 15-03-01 | 03 | 2 | EUQ-02, EUQ-08, EUQ-09 | manual | Writer agent instruction review (interface-aware, functional-first, boundaries) | N/A | ⬜ pending |
| 15-03-02 | 03 | 2 | EUQ-05 | manual | Generate command regeneration behavior review | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. This phase primarily modifies LLM prompt files (markdown), not Python scripts. The existing `write-scan-output.py` tests already validate key format acceptance which covers EUQ-06's data path. No new Python scripts are introduced, so no new test files are needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Interface detection + config persistence | EUQ-01 | Scan is LLM orchestration, not Python code | Run scan on test project, verify `user_interfaces` in scan output and `.docs.config.json` |
| Writer interface-aware generation | EUQ-02 | Writer is an LLM agent prompt | Run generate on web-UI project, verify click-path style procedures |
| End-user scan exclusion rules | EUQ-03 | scan-audience.md is an LLM prompt | Run scan, verify `pyproject.toml` and `migrations/` not indexed for end-users |
| Template 7-section structure | EUQ-04 | Template is a markdown file | Inspect template: 7 `## ` headings with correct PURPOSE/EXAMPLE/SYNTHESIZED/BOUNDARY comments |
| Old docs deleted + fresh generation | EUQ-05 | Generate behavior, not script logic | Run generate in initial mode, verify old USER_GUIDE replaced |
| SYNTHESIZED section support | EUQ-06 | Partially automated (key validation) | Verify scan produces entries with `synthesized_from` and empty `source_files` |
| BOUNDARY comment support | EUQ-07 | Agent prompt behavior | Verify scan skips bounded content, writer cross-references alternate docs |
| Functional-first pattern | EUQ-08 | Writer prompt behavior | Review generated sections: goal before procedure, expected results after steps |
| Cross-audience boundaries | EUQ-09 | Template + agent prompt behavior | Verify infrastructure content routes to devops, not USER_GUIDE |
| DOMAIN_SPECIFIC deletion | EUQ-10 | File deletion | Verify `DOMAIN_SPECIFIC.template.md` does not exist in `auto-doc/references/templates/end-users/` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
