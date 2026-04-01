---
phase: 18
slug: recursive-section-xml-core
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py --tb=short -q --no-header` |
| **Full suite command** | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py --tb=short -q --no-header`
- **After every plan wave:** Run `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 1 | XML-01 | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestBuildAndParse -x` | Rewrite needed | ⬜ pending |
| 18-01-02 | 01 | 1 | XML-02 | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestBuildAndParse::test_body_isolation -x` | New test | ⬜ pending |
| 18-01-03 | 01 | 1 | XML-03 | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestUpdateSectionRefs -x` | Rewrite needed | ⬜ pending |
| 18-01-04 | 01 | 1 | XML-04 | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestWalkSections -x` | New test class | ⬜ pending |
| 18-01-05 | 01 | 1 | XML-05 | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestFindSectionByPath -x` | New test class | ⬜ pending |
| 18-01-06 | 01 | 1 | XML-06 | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestAddSection -x` | New test | ⬜ pending |
| 18-01-07 | 01 | 1 | XML-07 | manual-only | Code review: no old-format parse path exists | N/A | ⬜ pending |
| 18-01-08 | 01 | 1 | XML-08 | manual-only | Review schema.md XML examples | N/A | ⬜ pending |
| 18-01-09 | 01 | 1 | XML-09 | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestRoundTrip -x` | New parameterized test class | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `auto-doc/scripts/tests/test_xml_doc.py` — rewrite all existing tests for nested model, add new test classes (TestWalkSections, TestFindSectionByPath, TestRoundTrip, TestGetSectionPaths)
- No framework install needed (pytest already present)
- No conftest changes needed (tests are self-contained with tempfile)

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| No dual-format reading code | XML-07 | Architectural constraint — absence of code paths, not a runtime behavior | Grep for old-format parse paths; verify none exist |
| Schema.md documents nested model with 2+ nesting levels | XML-08 | Documentation content review | Read schema.md; verify XML examples show nested sections |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
