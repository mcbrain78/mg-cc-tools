---
phase: 12-auto-doc-rename-and-cleanup
verified: 2026-03-22T12:00:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 12: Auto-Doc Rename and Cleanup Verification Report

**Phase Goal:** Rename the create-docs tool family to auto-doc and clean up dead code, orphaned agents, and latent bugs -- clearing the deck for all subsequent v1.1 work (phases 13-16)
**Verified:** 2026-03-22
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All 5 auto-doc commands are accessible under auto-doc/ with correct filenames | VERIFIED | `auto-doc.md`, `auto-doc-scan.md`, `auto-doc-generate.md`, `auto-doc-verify.md`, `auto-doc-add.md` all present; frontmatter `name:` fields confirm `mg:auto-doc`, `mg:auto-doc-add`, etc. |
| 2 | No create-docs or add-docs references exist outside .planning/ and docs/work-queue/ | VERIFIED | grep over all .md/.py/.sh/.toml/.json excluding .planning, docs, .git, session-analyzer returns zero hits (migration path in install.sh is the only surviving usage and is intentional) |
| 3 | Orphaned staleness-scanner.md is deleted | VERIFIED | `test -f auto-doc/agents/staleness-scanner.md` fails; 7 agents remain, none named staleness-scanner |
| 4 | install.sh migrates old create-docs installations before deploying auto-doc | VERIFIED | Lines 169-194 of install.sh: detects `create-docs.md` or `create-docs/` dir, removes stale command files and support dir, cleans manifest entry with inline python3 and non-fatal fallback |
| 5 | mg-install-lib.py workspace mapping uses auto-doc key | VERIFIED | Line 62: `"auto-doc": ".mg/docs"` |
| 6 | CLAUDE.md references auto-doc (not create-docs) as the documentation tool | VERIFIED | Line 42: "Complex tools (codebase-health, auto-doc)"; auto-doc pipeline subsection added |
| 7 | staleness-check.py CLI output is a dict with staleness_report key consumable by merge-scan.py | VERIFIED | Lines 273-277: `save_json(args.output, {"staleness_report": entries})` and `json.dump({"staleness_report": entries}, ...)`. Internal `check_staleness()` still returns bare list |
| 8 | add-note.py and classify-note.py use note_id field consistently matching the schema | VERIFIED | add-note.py lines 38, 79: `note.get("note_id", "")` and `"note_id": note_id`; classify-note.py line 153: `note["note_id"]` |
| 9 | add-note.py prints JSON with note_id to stdout for command file consumption | VERIFIED | Line 94: `print(json.dumps({"note_id": note_id}))` |
| 10 | Scan pipeline no longer calls check-references.py (verify-only concern) | VERIFIED | `grep "check-references" auto-doc/commands/auto-doc-scan.md` returns zero hits; verify pipeline still uses it (auto-doc-verify.md has references) |
| 11 | All tests pass with updated assertions reflecting the fixed behavior | VERIFIED | 106 tests pass (`python3 -m pytest auto-doc/scripts/tests/`); includes 1 new stdout JSON test for add-note.py |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `auto-doc/commands/auto-doc.md` | Renamed router command | VERIFIED | `name: mg:auto-doc` in frontmatter |
| `auto-doc/commands/auto-doc-add.md` | Renamed add command (non-trivial rename) | VERIFIED | `name: mg:auto-doc-add` in frontmatter |
| `auto-doc/install.sh` | Install script with migration path | VERIFIED | Lines 169-194 contain full migration block; COMMANDS array lists all 5 auto-doc names; SUPPORT_DIR is `auto-doc` |
| `auto-doc/tool.toml` | Tool metadata with updated paths | VERIFIED | Line 9: `paths = [".claude/auto-doc/scripts/"]` |
| `auto-doc/scripts/staleness-check.py` | Fixed CLI output wrapper for merge-scan.py compatibility | VERIFIED | `{"staleness_report": entries}` at both --output and stdout paths |
| `auto-doc/scripts/add-note.py` | Fixed note_id field and JSON stdout output | VERIFIED | `"note_id"` used throughout; `print(json.dumps({"note_id": note_id}))` on line 94 |
| `auto-doc/scripts/classify-note.py` | Fixed note_id field reading | VERIFIED | `note["note_id"]` on line 153 |
| `auto-doc/commands/auto-doc-scan.md` | Scan command without dead check-references.py call | VERIFIED | No `check-references` invocations; removed per plan |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `auto-doc/install.sh` | `mg-install-lib.py` | SUPPORT_DIR and COMMANDS array reference auto-doc | VERIFIED | COMMANDS array: `auto-doc auto-doc-scan auto-doc-generate auto-doc-verify auto-doc-add`; SUPPORT_DIR=`${TARGET_DIR}/auto-doc` |
| `install/scripts/mg-install-lib.py` | auto-doc workspace | WORKSPACE_DIRS mapping `"auto-doc": ".mg/docs"` | VERIFIED | Line 62 confirmed |
| `auto-doc/commands/auto-doc-generate.md` | `/mg:auto-doc-add` | HTML comment template strings | VERIFIED | Lines 378, 467, 473 all reference `/mg:auto-doc-add` |
| `auto-doc/scripts/staleness-check.py` | `auto-doc/scripts/merge-scan.py` | CLI output dict with staleness_report key | VERIFIED | dict wrapper confirmed at both output paths |
| `auto-doc/scripts/add-note.py` | `auto-doc/commands/auto-doc-add.md` | JSON stdout with note_id | VERIFIED | `json.dumps({"note_id": note_id})` to stdout |
| `auto-doc/scripts/add-note.py` | `auto-doc/references/schema.md` | note_id field matching schema contract | VERIFIED | `"note_id"` used consistently; no `"id"` references for note identity |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REN-01 | 12-01 | `create-docs/` renamed to `auto-doc/` with all 5 command files renamed | SATISFIED | Directory confirmed; all 5 command files present with correct names |
| REN-02 | 12-01 | Bulk `s/create-docs/auto-doc/g` applied to all non-historical files | SATISFIED | Verification grep returns zero create-docs hits outside migration path and exclusions |
| REN-03 | 12-01 | Explicit `s/add-docs/auto-doc-add/g` substitution in all non-trivial locations | SATISFIED | generate.md HTML comments use `auto-doc-add`; frontmatter `name: mg:auto-doc-add` confirmed |
| REN-04 | 12-01 | Cross-tool references updated in mg-install-lib.py, install.md (both copies), permission-hooks test data | SATISFIED | mg-install-lib.py line 62 confirmed; both install.md copies show `auto-doc`; test_permission_guard.py lines 999/1001/1033 use `/mg:auto-doc-add` |
| REN-05 | 12-01 | Migration path in `auto-doc/install.sh` detects old `create-docs` installation | SATISFIED | Lines 169-194 confirmed: detection, file removal, manifest cleanup |
| REN-06 | 12-01 | Orphaned `staleness-scanner.md` agent deleted | SATISFIED | File absent; 7 agents remain |
| REN-07 | 12-01 | Verification grep confirms zero `create-docs` or `add-docs` references outside exclusions | SATISFIED | Full grep over .md/.py/.sh/.toml/.json returns no hits outside migration path |
| FIX-C1 | 12-02 | Dead `check-references.py` invocation removed from scan pipeline Step 3 | SATISFIED | `grep "check-references" auto-doc-scan.md` returns zero hits |
| FIX-C2 | 12-02 | `staleness-check.py` CLI output wrapped in `{"staleness_report": entries}` | SATISFIED | Lines 273-277 confirmed |
| FIX-C3 | 12-02 | `note_id` field used consistently in `add-note.py` and `classify-note.py` | SATISFIED | Both files confirmed; no `["id"]` note-identity references remain |
| FIX-C4 | 12-02 | `add-note.py` outputs JSON `{"note_id": ...}` to stdout | SATISFIED | Line 94 confirmed |
| FIX-C5 | 12-02 | All existing tests pass after rename and bug fixes with updated assertions | SATISFIED | 106 tests pass (105 original + 1 new stdout JSON test) |

**All 12 requirements satisfied. No orphaned requirements.**

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `auto-doc/scripts/__pycache__/` | n/a | __pycache__ directories present | Info | Present in .gitignore, not tracked, freshly generated by test run after rename -- not stale rename artifacts |

No blockers or warnings found.

### Human Verification Required

None. All phase 12 concerns are mechanical (rename, grep-verified clean state, logic fixes with test coverage) and fully verifiable programmatically.

### Gaps Summary

No gaps. All 11 observable truths verified, all 12 requirements satisfied, all key links wired, all 4 commits confirmed in git log (`82dc40f`, `c76dbfb`, `a3f9c5b`, `497980d`).

The phase achieved its goal: the create-docs tool family is fully renamed to auto-doc, dead code and orphaned agents are removed, latent bugs are fixed with updated tests, and the codebase is clean for phases 13-16.

---

_Verified: 2026-03-22_
_Verifier: Claude (gsd-verifier)_
