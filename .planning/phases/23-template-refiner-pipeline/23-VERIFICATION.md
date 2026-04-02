---
phase: 23-template-refiner-pipeline
verified: 2026-04-02T20:00:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 23: Template Refiner Pipeline Verification Report

**Phase Goal:** prepare-templates command and template-refiner agent produce project-specific refined templates with ###/#### headings, PURPOSE comments, and structural EXAMPLE blocks from scan data and shallow source exploration
**Verified:** 2026-04-02
**Status:** passed
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running /mg:auto-doc-prepare-templates loads config, reads scan data, and spawns one refiner agent per audience/document pair | VERIFIED | Command reads `.mg/docs/.docs.config.json` (with `{GLOBAL_CONFIG}` fallback), reads `.mg/docs/docs-scan.json`, iterates `config.audiences`, and spawns sequential Agent calls per pair |
| 2 | The command passes all required context (paths, scan date, audience, document) to each refiner agent | VERIFIED | Agent prompt in command includes: project_root, generic template path (via {TEMPLATES_DIR}), scan_data_path, output_path, audience, document, scan_date, scripts_dir -- all 8 fields present |
| 3 | Only audience-specific documents are processed -- OVERVIEW and GLOSSARY are excluded | VERIFIED | Line 69: "Do NOT process `config.shared_documents` (OVERVIEW, GLOSSARY)"; refiner MUST NOT rule line 127 reinforces exclusion |
| 4 | Output directories are created before agent spawning | VERIFIED | Step 3 runs `mkdir -p .mg/docs/templates/{audience}/` before Step 4 spawning |
| 5 | install.sh deploys the new command to target projects | VERIFIED | `auto-doc-prepare-templates` appears in COMMANDS array (line 36) and in both help text sections (lines 88, 427) |
| 6 | Refiner reads generic template and preserves all ## heading text and order verbatim | VERIFIED | MUST rule: "preserve `##` heading text EXACTLY"; MUST NOT rule: "MUST NOT change `##` heading text in any way -- not even capitalization or punctuation" |
| 7 | Refiner performs shallow source exploration: get_symbols_overview for Python, full Read for non-code files | VERIFIED | Lines 49-51 specify: Python files -> `get_symbols_overview` (Serena), non-code files (.service, .yaml, etc.) -> full Read, with fallback defined for both |
| 8 | PURPOSE comments contain project-specific structural facts grounded in source evidence | VERIFIED | MUST rule: "ground every PURPOSE comment in observable source evidence (class counts, service names, config entries, API names). Cite what you found." |
| 9 | EXAMPLE blocks contain only generic format demonstrations with placeholder data | VERIFIED | MUST rule: "use `...` placeholders and generic column headers in EXAMPLE blocks"; MUST NOT: "MUST NOT put project-specific values...in EXAMPLE blocks" |
| 10 | OPTIONAL sections are resolved based on source evidence: keep if any evidence, drop if none | VERIFIED | Lines 61-64: conservative keep-if-any-evidence heuristic; MUST NOT rule: "MUST NOT leave any `<!-- OPTIONAL -->` markers in the refined template" |
| 11 | Refined template includes REFINED metadata comment with current date and scan date | VERIFIED | Line 73: `<!-- REFINED: {today's date}, scan: {scan_date} -->`; MUST rule at line 116 enforces it |
| 12 | Same scan data produces structurally equivalent heading trees on re-run | VERIFIED | Lines 59-60: "Make heading decisions deterministically based on evidence"; MUST rule: "The same source files should produce the same heading structure" |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `auto-doc/commands/auto-doc-prepare-templates.md` | Orchestrator command for template refinement pipeline | VERIFIED | 145 lines (exceeds min 80); frontmatter correct; contains complete 5-step orchestration flow |
| `auto-doc/install.sh` | Updated COMMANDS array with auto-doc-prepare-templates | VERIFIED | Entry at line 36; help text at lines 88 and 427 |
| `auto-doc/agents/template-refiner.md` | Refiner agent definition for per-document template refinement | VERIFIED | 145 lines (exceeds min 100); Role, Inputs, Process, Critical Rules, Output Format all present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| auto-doc/commands/auto-doc-prepare-templates.md | {AGENTS_DIR}/template-refiner.md | Agent tool spawning | WIRED | Line 99: `Read and follow the instructions in: {AGENTS_DIR}/template-refiner.md` |
| auto-doc/commands/auto-doc-prepare-templates.md | .mg/docs/docs-scan.json | Read scan data | WIRED | Lines 44, 52-56, 103 reference docs-scan.json |
| auto-doc/install.sh | auto-doc/commands/auto-doc-prepare-templates.md | COMMANDS array registration | WIRED | Line 36: `auto-doc-prepare-templates` in COMMANDS array |
| auto-doc/agents/template-refiner.md | auto-doc/scripts/get-section-sources.py | Bash invocation | WIRED | Lines 42-45: `python3 {scripts_dir}/get-section-sources.py --scan-file ... --key ...`; script exists |
| auto-doc/agents/template-refiner.md | .mg/docs/docs-scan.json | Read scan data for source_material_index | WIRED | Line 24: `Read scan data from scan_data_path -- extract source_material_index and project_model` |
| auto-doc/agents/template-refiner.md | next-heading.py parse_template() | Output format compatibility | WIRED | Lines 142-145 explicitly state output must be parseable by parse_template(), specifying ##-#### headings with PURPOSE/EXAMPLE HTML comments |
| auto-doc/install.sh | auto-doc/agents/template-refiner.md | agents/*.md wildcard copy | WIRED | Lines 260-261: `cp "${SCRIPT_DIR}"/agents/*.md "${SUPPORT_DIR}/agents/"` |
| auto-doc/commands/auto-doc-prepare-templates.md | auto-doc/scripts/list-optional-sections.py | Passed as scripts_dir to refiner | WIRED | Line 115 mentions refiner can invoke list-optional-sections.py; script exists |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TRF-01 | 23-01-PLAN.md | Running `/mg:auto-doc-prepare-templates` reads scan data and produces per-audience refined templates at `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` | SATISFIED | Command reads docs-scan.json; output path in agent prompt is `{project_root}/.mg/docs/templates/{audience}/{document}.template.md` |
| TRF-02 | 23-02-PLAN.md | Each refiner agent performs shallow source exploration (symbol overviews for code, full reads for config files) and decides what ###/#### headings each ## section needs | SATISFIED | Lines 49-59 of template-refiner.md define exact shallow exploration rules by file type |
| TRF-03 | 23-02-PLAN.md | PURPOSE comments contain project-specific structural facts (counts, names, relationships) grounded in scan data and source exploration | SATISFIED | MUST rules at lines 117, 120 enforce evidence-grounding and citation |
| TRF-04 | 23-02-PLAN.md | EXAMPLE blocks are generic format demonstrations with placeholder data, containing no project-specific values | SATISFIED | MUST/MUST NOT rules at lines 118, 125 enforce the boundary |
| TRF-05 | 23-02-PLAN.md | ## sections preserve the same slugs and structure from the generic template | SATISFIED | MUST NOT rule at line 124: "MUST NOT change ## heading text in any way -- not even capitalization or punctuation" |
| TRF-06 | 23-01-PLAN.md, 23-02-PLAN.md | The refined template fully replaces the generic template for the writer | SATISFIED | template-refiner.md line 7: "The refined template fully replaces the generic template for the writer -- the writer sees only the refined version"; agent writes output to `output_path` via Write tool |
| TRF-07 | 23-02-PLAN.md | Running `prepare-templates` twice on the same scan data produces structurally equivalent refined templates (same heading tree, same PURPOSE topics) | SATISFIED | MUST rule at line 119: "make heading decisions deterministically based on source evidence. The same source files should produce the same heading structure" |

**Requirements coverage: 7/7 (100%). No orphaned requirements detected.**

---

### Anti-Patterns Found

| File | Pattern | Severity | Assessment |
|------|---------|----------|------------|
| auto-doc/agents/template-refiner.md | "placeholder" on lines 3, 83, 104, 118 | Info | NOT a stub -- these are instructional references to `...` placeholder data that writers must use in EXAMPLE blocks. Legitimate content. |

No blocker or warning anti-patterns found.

---

### Human Verification Required

The following behaviors require human testing to confirm they work end-to-end at runtime:

#### 1. Full pipeline execution

**Test:** Install the tool into a project with a valid `docs-scan.json`, run `/mg:auto-doc-prepare-templates`, and inspect the refined templates produced.
**Expected:** One `.template.md` file per audience/document pair in `.mg/docs/templates/{audience}/`, each containing DIATAXIS, AUDIENCE, REFINED metadata comments; ## headings matching the generic template verbatim; project-specific PURPOSE comments; generic EXAMPLE blocks with `...` placeholders.
**Why human:** This is an LLM agent pipeline -- verifying that the spawned template-refiner agent actually reads source files correctly, infers appropriate headings, and formats output to spec requires runtime execution.

#### 2. OPTIONAL section resolution

**Test:** Find a generic template with at least one `<!-- OPTIONAL -->` section. Run prepare-templates on a project where that section has no source evidence, then on a project where it does.
**Expected:** Section dropped (no evidence) vs section kept with child headings (evidence found).
**Why human:** OPTIONAL resolution is a judgment call made by the LLM agent at runtime -- verifying the conservative heuristic is actually applied correctly requires execution.

#### 3. Shallow exploration ceiling enforcement

**Test:** Run prepare-templates on a project with Python source files. Confirm the refiner uses `get_symbols_overview` and does not read function bodies.
**Expected:** No function implementation logic appears in PURPOSE comments -- only class names, function names, module-level structure.
**Why human:** The "no function bodies" constraint is an instruction to the LLM agent; it cannot be verified by static code analysis.

---

### Gaps Summary

No gaps found. All 12 truths verified, all 3 artifacts substantive and wired, all 8 key links confirmed, all 7 requirements satisfied, 0 orphaned requirements.

The phase goal is achieved: the `prepare-templates` command and `template-refiner` agent are fully defined with the required behaviors. The test suite passes (732/732 tests). Human verification is needed only for LLM runtime behavior, not for structural completeness.

---

_Verified: 2026-04-02_
_Verifier: Claude (gsd-verifier)_
