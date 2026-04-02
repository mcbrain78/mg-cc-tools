---
phase: 24-writer-orient-write-integration
verified: 2026-04-02T20:00:00Z
status: passed
score: 19/19 must-haves verified
re_verification: false
---

# Phase 24: Writer Orient-Write Integration Verification Report

**Phase Goal:** devops-writer uses next-heading.py orient-then-write loop, generate command detects and routes refined templates, and end-to-end pipeline produces complete documents from refined templates
**Verified:** 2026-04-02
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | generate-setup.py JSON output includes `refined_templates` dict mapping audience/document to path or null | VERIFIED | Lines 443-444: `"refined_templates": refined_templates, "stale_templates": stale_templates` in `main()` result dict |
| 2 | generate-setup.py JSON output includes `stale_templates` list for templates whose scan date is older than current scan | VERIFIED | `stale_templates` populated and returned by `detect_refined_templates()`, appended in `main()` output at line 444 |
| 3 | Refined template detected when `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` exists | VERIFIED | `detect_refined_templates()` line 343: `path = os.path.join(templates_base, aud_name, f"{doc}.template.md")` then `os.path.isfile(path)` |
| 4 | Missing refined template returns null in `refined_templates` dict (not an error) | VERIFIED | Line 350: `refined[aud_name][doc] = None` for missing/no-heading case |
| 5 | Stale detection compares REFINED comment scan date to scan_date using date-only (YYYY-MM-DD) comparison | VERIFIED | `_check_stale()` line 317-320: `refined_scan_date = m.group(1)...[:10]`, `current_date = current_scan_date[:10]`, then `current_date > refined_scan_date` |
| 6 | Malformed or unreadable refined template is treated as stale | VERIFIED | `_check_stale()`: `except OSError: return True` and `if not m: return True` |
| 7 | Refined template with no ## headings is treated as absent (null) | VERIFIED | `_has_headings()` returns False when no `## ` line found; `detect_refined_templates()` line 344 gates on `_has_headings(path)` |
| 8 | devops-writer processes documents using orient-then-write loop driven by next-heading.py | VERIFIED | devops-writer.md step 2c: full LOOP with orient/write/done handling calling `next-heading.py` repeatedly |
| 9 | Writer reads source files once per ## section during orient phase, not per heading | VERIFIED | Process section 2c: source file reads occur only in `type = "orient"` branch, not in `type = "write"` branch |
| 10 | Writer emits one write-section.py call per heading in the write phase | VERIFIED | Process section 2c write branch: `write-section.py` called for each `type = "write"` response |
| 11 | Writer splits heading_path on / to derive --section and --parent arguments | VERIFIED | Process section 2c: "Split heading_path on /: The last segment is section_slug. Everything before it is parent_path." + table with 3 examples |
| 12 | Writer sees only the refined template path (never reads generic template) | VERIFIED | Principles: "Do NOT read the refined template directly -- next-heading.py reads it for you." No Templates dir input. Receives `refined_template_path`. |
| 13 | Writer never decides what headings to create -- template structure comes entirely from next-heading.py | VERIFIED | Role (line 7): "You never decide what headings to create -- that is the template's job via next-heading.py." |
| 14 | Writer calls next-heading.py in sequence: orient -> write x N -> orient -> write x N -> done | VERIFIED | Process section 2c loop: both orient and write branches call `next-heading.py again with the same arguments` before iterating |
| 15 | Generate command routes devops writers through orient-write prompt when refined template exists | VERIFIED | auto-doc-generate.md lines 140-169: `For each devops document where refined_templates["devops"][DOCUMENT] is not null` -> dedicated orient-write Agent prompt with `refined_template_path` and `state_file_path` |
| 16 | Generate command falls back to standard prompt for devops when no refined template exists | VERIFIED | Line 171: "For each devops document where refined_templates["devops"][DOCUMENT] is null, use the standard prompt (same as non-devops audiences, with Templates dir)." |
| 17 | Non-devops audiences always use standard prompt (unchanged behavior) | VERIFIED | Lines 173-195: "For all other audiences (end-users, developers, agents): Always use the standard prompt (current behavior, unchanged)" with original Agent template |
| 18 | Generate command prints stale warning when refined templates are stale | VERIFIED | Lines 57-63: `if stale_templates is non-empty, print a warning ... This is a warning only -- do NOT abort.` |
| 19 | State file path is scoped per audience+document to prevent collision | VERIFIED | Line 162: `State file path: {tmp_dir}/heading-state-devops-{DOCUMENT}.json` — unique per document |

**Score:** 19/19 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `auto-doc/scripts/generate-setup.py` | `detect_refined_templates()`, `_check_stale()`, `_has_headings()` functions; `refined_templates` + `stale_templates` in JSON output | VERIFIED | All 4 functions present (including `_read_scan_date()`). JSON output keys at lines 443-444. File is 450 lines, substantive. |
| `auto-doc/scripts/tests/test_generate_setup.py` | Tests for refined template detection and stale warning | VERIFIED | 3 new test classes: `TestCheckStale` (line 456), `TestDetectRefinedTemplates` (line 512), `TestRefinedTemplatesCLI` (line 610). 16 new test methods. All 40 tests pass. |
| `auto-doc/agents/devops-writer.md` | Rewritten devops writer agent with orient-write loop | VERIFIED | 209 lines. 9 references to `next-heading.py`, 5 to `orient`, 8 to `heading_path`. New inputs: `refined_template_path`, `state_file_path`, `scripts_dir`. Full loop with orient/write/done handling. |
| `auto-doc/commands/auto-doc-generate.md` | Refined template routing in Stage 2, stale warning, per-document state file paths | VERIFIED | 491 lines. `refined_templates` parsed from setup output (lines 52-53). Stale warning (lines 57-63). Conditional orient-write routing in Stage 2 (lines 140-204). |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `auto-doc/scripts/generate-setup.py` | `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` | `os.path.isfile` check in `detect_refined_templates` | WIRED | Line 344: `if os.path.isfile(path) and _has_headings(path)` |
| `auto-doc/scripts/generate-setup.py` | `docs-scan.json` `scan_date` field | `_check_stale` date comparison | WIRED | `_read_scan_date()` reads scan file; `detect_refined_templates()` receives `scan_date`; `_check_stale()` compares `[:10]` slices |
| `auto-doc/agents/devops-writer.md` | `auto-doc/scripts/next-heading.py` | Bash calls in loop with `--state-file --template --scan-file --document` | WIRED | Lines 46-51: full `next-heading.py` call with all 4 required args. Called again at end of both orient and write branches. |
| `auto-doc/agents/devops-writer.md` | `auto-doc/scripts/write-section.py` | Bash calls per heading with `--section` and `--parent` from `heading_path` | WIRED | Lines 93-102: `write-section.py` call with `--section {section_slug}` and `[--parent {parent_path}]` |
| `auto-doc/commands/auto-doc-generate.md` | `auto-doc/scripts/generate-setup.py` | JSON output includes `refined_templates` dict consumed for routing decisions | WIRED | Lines 52-53: `refined_templates` and `stale_templates` parsed from setup JSON; used in routing logic at lines 140-171 |
| `auto-doc/commands/auto-doc-generate.md` | `auto-doc/agents/devops-writer.md` | Agent prompt passes `refined_template_path` and `state_file_path` | WIRED | Lines 161-162: `Refined template path:` and `State file path:` in orient-write Agent prompt |
| `auto-doc/commands/auto-doc-generate.md` | `auto-doc/scripts/next-heading.py` | State file path for `heading-state-{audience}-{DOCUMENT}.json` created in tmp | WIRED | Line 162: `State file path: {tmp_dir}/heading-state-devops-{DOCUMENT}.json`; generate-setup.py line 198: `"heading-state-*.json"` in cleanup patterns |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| OWI-01 | 24-02 | devops-writer processes documents in two-phase orient-then-write loop | SATISFIED | devops-writer.md Process section 2c: full orient/write/done loop with source file reads in orient phase only |
| OWI-02 | 24-01 | generate command detects refined templates at project-level path, falls back to generic when absent | SATISFIED | `detect_refined_templates()` in generate-setup.py; returns null for missing files; `refined_templates` dict in JSON output consumed by generate command |
| OWI-03 | 24-01 | generate command prints warning when refined template is stale | SATISFIED | auto-doc-generate.md lines 57-63: non-blocking stale warning when `stale_templates` is non-empty |
| OWI-04 | 24-02 | Writer produces content for every heading in template, skipping none and inventing none | SATISFIED | Writer role states it never decides headings; loop driven entirely by next-heading.py responses; done only when `done: true` returned |
| OWI-05 | 24-02 | When refined template is present, writer sees only the refined template | SATISFIED | Principles: "Do NOT read the refined template directly"; orient-write prompt provides `refined_template_path`, not `Templates dir` |
| OWI-06 | 24-03 | Content quality and reference accuracy at least as good as previous approach | NEEDS HUMAN | Quality claim requires runtime testing — cannot be verified statically. The structural preconditions are in place (all source reading, refs format, style guide, conventions preserved). |
| OWI-07 | 24-03 | Only devops-writer is modified in this phase; all other writers are unchanged | SATISFIED | Git log confirms only `auto-doc/agents/devops-writer.md`, `auto-doc/scripts/generate-setup.py`, and `auto-doc/commands/auto-doc-generate.md` modified in phase 24 commits. end-user-writer.md, developer-writer.md, agent-writer.md, glossary-writer.md, overview-writer.md last modified before phase 24. |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `generate-setup.py` | 76, 85 | `pass` in exception handlers | Info | Legitimate exception handling in `read_project_root()` — not stubs. JSON parse fallback logic. |

No blockers. No stubs. No TODO/FIXME/placeholder anti-patterns in any modified file.

---

### Human Verification Required

#### 1. Content Quality of Orient-Write Pipeline (OWI-06)

**Test:** Run `/mg:auto-doc-generate` on a project that has a refined devops template (a `.mg/docs/templates/devops/OPERATIONS.template.md`), then inspect the generated OPERATIONS.md.
**Expected:** Generated document covers every heading in the refined template, contains accurate technical content drawn from source files, and includes properly typed refs. Quality should be equal to or better than the previous template-reading approach.
**Why human:** Static analysis cannot verify content quality, reference accuracy, or whether the orient-then-write loop produces coherent prose. Requires a live pipeline run with real source code.

---

### Gaps Summary

No gaps. All automated truths verified. One item (OWI-06) requires human verification of runtime output quality, but all structural preconditions for quality are present: source reading conventions preserved, typed refs format intact, style guide and glossary inputs passed, devops conventions section unchanged.

---

_Verified: 2026-04-02_
_Verifier: Claude (gsd-verifier)_
