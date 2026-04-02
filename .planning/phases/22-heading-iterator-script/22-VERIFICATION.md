---
phase: 22-heading-iterator-script
verified: 2026-04-02T19:00:00Z
status: passed
score: 7/7 must-haves verified
---

# Phase 22: Heading Iterator Script Verification Report

**Phase Goal:** next-heading.py parses refined templates, manages heading queue state, and returns orient/write/done responses with correct depth-first ordering and source file grouping
**Verified:** 2026-04-02
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Calling next-heading.py with --state-file, --template, --scan-file, --document produces JSON to stdout | VERIFIED | `main()` parses all 4 required args via argparse; 39 tests invoke via subprocess and assert JSON output |
| 2 | First call parses template and persists heading queue to state file; subsequent calls read from state | VERIFIED | `load_json(args.state_file)` returns None on first call triggering parse; `test_subsequent_call_uses_state_not_template` deletes template and confirms second call succeeds from state |
| 3 | Orient response appears at each ## section boundary with slug, heading_outline, and source_files | VERIFIED | `build_emission_queue` emits orient dict with all three fields before each section's writes; `TestOrientResponse` class validates all fields |
| 4 | Write response appears for every heading with heading_path, level, purpose, example; ## writes omit parent_path | VERIFIED | `_walk_headings_depth_first` yields every heading; parent_path added only when `/` in path; `test_section_level_write_omits_parent_path` and `test_child_write_has_parent_path` confirm |
| 5 | Done response appears after all headings with headings_processed count | VERIFIED | `queue.append({"done": True, "headings_processed": total_headings})` in `build_emission_queue`; `test_done_count_matches_writes` verifies count equals write count |
| 6 | Output sequence is depth-first: orient, writes for that section, orient, writes, ..., done | VERIFIED | `test_full_sequence_nested` asserts exact sequence `["orient","write","write","write","orient","write","done"]`; `test_deep_nesting_depth_first` verifies ####-level grandchild ordering |
| 7 | heading_path last segment maps to --section, preceding segments map to --parent for write-section.py | VERIFIED | `parent_path = heading["path"].rsplit("/", 1)[0]`; `test_parent_path_is_preceding_segments` and `test_last_segment_is_section_slug` validate the convention |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `auto-doc/scripts/next-heading.py` | Script-gated heading iterator | VERIFIED | 330 lines (min 80); exports `main`, `parse_template`, `build_emission_queue`; fully wired |
| `auto-doc/scripts/tests/test_next_heading.py` | TDD test suite covering all 7 HIT requirements | VERIFIED | 731 lines (min 150); 39 tests, 7 test classes mapping 1:1 to HIT-01 through HIT-07; all pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `auto-doc/scripts/next-heading.py` | `auto-doc/scripts/lib/json_io.py` | `from lib.json_io import load_json, save_json` | WIRED | Import present at line 29; `load_json` and `save_json` called in `main()` |
| `auto-doc/scripts/next-heading.py` | `write-section.py slugify_heading` | `def slugify_heading` copied verbatim | WIRED | `slugify_heading` defined at line 32 with identical algorithm; used throughout `parse_template` and helper functions |
| `auto-doc/scripts/tests/test_next_heading.py` | `auto-doc/scripts/next-heading.py` | `subprocess.run` via `SCRIPT` constant | WIRED | `SCRIPT = os.path.join(SCRIPTS_DIR, "next-heading.py")` at line 14; all test invocations use `[sys.executable, SCRIPT, ...]` |

Note: The PLAN's key_link pattern `subprocess\.run.*next-heading\.py` does not literally match the test file because the test uses a `SCRIPT` constant (defined on line 14 as the path to `next-heading.py`) rather than an inline string. The link is functionally wired — every `subprocess.run` call in the test invokes `next-heading.py` through the `SCRIPT` variable.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| HIT-01 | 22-01-PLAN.md | Four required CLI arguments; missing any exits with code 2 | SATISFIED | `argparse` with `required=True` on all 4 args; `TestCLI` class with 5 tests all pass |
| HIT-02 | 22-01-PLAN.md | First call parses template + persists state; subsequent calls skip parse; multi-line comments extracted; EXAMPLE headings excluded | SATISFIED | State machine in `main()`; `test_headings_in_example_not_treated_as_real` confirms comment-range exclusion; `test_multiline_purpose_extracted` confirms DOTALL regex |
| HIT-03 | 22-01-PLAN.md | Orient at each ## boundary with section slug, heading_outline, source_files from scan | SATISFIED | `build_emission_queue` constructs orient before each section; `TestOrientResponse` 5 tests all pass |
| HIT-04 | 22-01-PLAN.md | Write for every heading; ## omits parent_path (absent, not null); ### and below include parent_path | SATISFIED | `"/" in heading["path"]` guard ensures correct presence/absence; `TestWriteResponse` 8 tests all pass |
| HIT-05 | 22-01-PLAN.md | Done after all headings with headings_processed count; idempotent on repeated calls | SATISFIED | Done item appended at queue end; index not advanced past done; `TestDoneResponse` 4 tests all pass |
| HIT-06 | 22-01-PLAN.md | Depth-first ordering: orient then writes per section; source_files only in orient | SATISFIED | Queue built by `build_emission_queue` in strict orient-then-depth-first order; `TestDepthFirstOrdering` 5 tests all pass |
| HIT-07 | 22-01-PLAN.md | Slash-separated heading_path; last segment = --section; preceding = --parent | SATISFIED | `rsplit("/", 1)[0]` for parent_path; `TestHeadingPathConvention` 5 tests all pass |

No orphaned requirements. All 7 HIT requirements declared in the PLAN are covered and marked complete in REQUIREMENTS.md.

### Anti-Patterns Found

None. No TODO/FIXME/HACK/PLACEHOLDER comments found in `next-heading.py`. No stub implementations. No empty returns.

### Human Verification Required

None. All behaviors are verifiable programmatically and confirmed by the passing test suite.

### Test Results

- `test_next_heading.py`: 39/39 tests passed
- Full `auto-doc/scripts/tests/` suite: 732/732 passed, 1 deprecation warning (pre-existing in `test_write_section.py`, unrelated to phase 22)
- Commits documented in SUMMARY: `976c628` (RED) and `fa04ddf` (GREEN) both confirmed present in git log

### Summary

Phase 22 goal is fully achieved. `next-heading.py` parses refined templates via regex-based comment-range exclusion, manages flat emission queue state in a JSON state file, and returns orient/write/done JSON responses in correct depth-first order with source file grouping at `##` section boundaries. All 7 HIT requirements are satisfied with comprehensive test coverage. The full 732-test suite passes with no regressions.

---
_Verified: 2026-04-02_
_Verifier: Claude (gsd-verifier)_
