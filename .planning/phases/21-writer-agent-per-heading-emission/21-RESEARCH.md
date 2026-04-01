# Phase 21: Writer Agent Per-Heading Emission - Research

**Researched:** 2026-04-01
**Domain:** LLM agent prompt engineering, markdown section emission, XML pipeline integration
**Confidence:** HIGH

## Summary

Phase 21 changes the granularity at which writer agents call `write-section.py`: instead of one call per `##` heading (which bundles all `###`/`####` subsections into a single body), writers call once for the `##` intro and once for each child heading, using the `--parent` flag to place children correctly in the state tree.

The infrastructure for this is already complete from Phases 18-20: `write-section.py` supports `--parent` (with slash-separated paths for grandchildren), finalize assembles nested state trees into nested XML, `sync-edits-to-xml.py` reconstructs hierarchy from heading levels, and `assemble-markdown.py` walks nested sections depth-first. The section marker `<!-- section: slug -->` is injected by `write-section.py` for every section regardless of depth. The only work remaining is updating three writer agent `.md` files to change their emission loop from "one call per `##`" to "one call per heading at every level."

**Primary recommendation:** This is a prompt-only change to three agent files (`devops-writer.md`, `glossary-writer.md`, `overview-writer.md`) plus end-to-end verification tests. No Python script changes are needed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Instead of one `write-section.py` call per `##` heading, the writer calls it once for the `##` intro and once for each `###`, `####`, etc. heading within that section
- Each call emits a small body (5-40 lines) with precisely scoped `typed_refs`
- The writer knows exactly which entities it referenced because it just wrote about them -- ref-assignment problem shrinks from "which of 30 refs belong to this 200-line body" to "which refs did I just use in these 3 paragraphs"
- Agent prompts change from "for each `##` section, write content and call `write-section.py`" to "for each `##` section, write the intro and call `write-section.py`, then for each `###` heading write its content and call `write-section.py` with `--parent` set to the `##` slug, then for each `####` heading call with `--parent` set to the `##/###` path"
- Only current-format agents: `devops-writer.md`, `glossary-writer.md`, `overview-writer.md` are updated
- `end-user-writer.md`, `developer-writer.md`, and `agent-writer.md` are NOT updated -- stale format, separate modernization effort
- Writer markdown output (prose and heading structure) is identical to the current output -- only emission granularity changes
- `<!-- section: slug -->` markers at every heading level in generated documents, same marker pattern regardless of depth
- Each writer must emit `typed_refs` that correspond exactly to the body being written (D6)
- A ref in parent's intro that only appears in child content must be moved to the child's refs

### Claude's Discretion
- Exact prompt wording for the recursive emission loop in each writer agent
- Whether to add a shared "nested emission" instruction block referenced by all writers or inline the pattern in each
- How overview-writer.md handles nesting (overview may not have `###` headings)
- Test strategy for end-to-end verification -- which road-runner documents to test against

### Deferred Ideas (OUT OF SCOPE)
- Stale writer modernization (`end-user-writer.md`, `developer-writer.md`, `agent-writer.md`) -- separate effort
- Content restructuring (adding/removing headings) -- out of scope per D8
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WHE-01 | Writer agents call write-section.py once per heading (intro, `###`, `####`, etc.) with the ancestor slug path as `--parent`, producing per-heading XML sections instead of one section per `##` heading | Supported by existing `--parent` flag in write-section.py (Phase 19), nested state tree accumulation, and finalize nested assembly. Prompt changes only needed in 3 agent .md files |
| WHE-02 | Only `devops-writer.md`, `glossary-writer.md`, and `overview-writer.md` are updated; stale-format writers are not modified | Verified: these 3 files use the current write-section.py pattern; the other 3 use a different/older pattern |
| WHE-03 | Generated markdown output (prose and heading structure) is identical to current output -- only emission granularity changes | Ensured by finalize's `_collect_all_sections_depth_first` assembly which concatenates in depth-first order; section markers are already injected per-section by write-section.py |
| WHE-04 | `<!-- section: slug -->` markers appear at every heading level using the same marker pattern regardless of depth | Already implemented: write-section.py line 186-190 injects `<!-- section: {section_name} -->` for every call regardless of `--parent`. No code change needed |
| WHE-05 | Each write-section.py call's `typed_refs` correspond exactly to the body emitted in that call | Enforced by prompt design: the writer emits a small body (5-40 lines) and immediately knows which refs it just used. Prompt wording must make this constraint explicit |
| WHE-06 | End-to-end verification confirms round-trip fidelity and ref precision across the full pipeline | Requires new integration tests that build nested state via CLI calls, finalize, assemble, and verify round-trip through sync-edits-to-xml |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| write-section.py | Current (Phase 19) | Section accumulation with `--parent` support | Already supports full nesting -- no changes needed |
| assemble-markdown.py | Current (Phase 19) | Walk nested XML sections depth-first into .md | Already walks nested sections -- no changes needed |
| sync-edits-to-xml.py | Current (Phase 20) | Round-trip sync using heading-level tree reconstruction | Already reconstructs heading hierarchy -- no changes needed |
| verify-xml-refs.py | Current (Phase 20) | Verify typed_refs against codebase | Already walks nested XML sections -- no changes needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| lib/xml_doc.py | Current | XML document tree manipulation | Used by finalize, not directly by agent prompts |
| lxml | Existing | XML parsing/serialization | Transitive dependency of xml_doc |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Shared instruction block | Inline per-writer | Shared block reduces duplication but adds indirection; inline is simpler since only 3 writers are affected and each has different nesting depth (devops deep, glossary/overview shallow) |

**Recommendation on shared vs inline:** Inline the pattern in each writer. Only 3 agents need updating. Each has materially different nesting characteristics (devops has `###` heavily; glossary has no `###`; overview has no `###`). A shared block would need conditional logic that adds complexity without saving much. Each agent is ~150 lines; the emission loop is ~30 lines of that.

## Architecture Patterns

### Current Writer Emission Pattern (to be replaced)
```
For each ## section:
  1. Generate full content (## heading + all ### and #### content)
  2. Write content file with everything
  3. Write refs file with ALL refs for the entire section
  4. Call write-section.py --section {slug}
```

### New Per-Heading Emission Pattern (target)
```
For each ## section:
  1. Generate intro content (## heading + text before first ###)
  2. Write intro content file
  3. Write refs file with ONLY intro refs
  4. Call write-section.py --section {slug}

  For each ### heading within this ## section:
    1. Generate ### content (### heading + text before first ####)
    2. Write content file
    3. Write refs file with ONLY this heading's refs
    4. Call write-section.py --section {child-slug} --parent {parent-slug}

    For each #### heading within this ### heading:
      1. Generate #### content
      2. Write content file
      3. Write refs file with ONLY this heading's refs
      4. Call write-section.py --section {grandchild-slug} --parent {parent-slug}/{child-slug}
```

### Writer-Specific Nesting Expectations

**devops-writer.md:** Heavy nesting. The OPERATIONS template has 7 `##` sections each containing 2-5 `###` headings. The TROUBLESHOOTING template has 6 `##` sections each containing 2-4 `###` headings. Total: ~13 `##` sections with ~40 `###` headings across both documents. No `####` headings in templates currently, but the agent may generate them.

**glossary-writer.md:** No nesting expected. The GLOSSARY template has only `##` sections (System Concepts, Domain Terms, Technical Terms, etc.). Terms within sections are not `###` headings -- they are bold-text entries within the `##` body. The emission loop changes structurally but will almost always produce the same behavior (one call per `##`, no children).

**overview-writer.md:** No nesting expected. The OVERVIEW template has 4 `##` sections (System Purpose, Key Concepts, Architecture at a Glance, Audience Guide). None have `###` headings in the template examples. Same as glossary: the structural change is needed for consistency but will rarely produce child sections.

### Temp File Naming Convention

Current pattern for files:
```
{TMP_DIR}/section-{audience}-{DOCUMENT}-{section-slug}.md
{TMP_DIR}/refs-{audience}-{DOCUMENT}-{section-slug}.json
```

For nested sections, the slug is the leaf slug (not the full path), so naming stays the same:
```
{TMP_DIR}/section-devops-OPERATIONS-etl-run-logging.md
{TMP_DIR}/refs-devops-OPERATIONS-etl-run-logging.json
```

The `--parent` flag on the CLI call handles placement; the temp file name only needs to be unique, which the leaf slug provides within a single document.

### Section Marker Injection

`write-section.py` (line 186-190) already injects `<!-- section: {section_name} -->` before the content if not already present. The `section_name` is the `--section` argument (the leaf slug), not the full path. This matches the existing marker format and is consumed by `sync-edits-to-xml.py` which uses heading levels (not marker paths) to reconstruct hierarchy.

**Key insight:** The marker uses the leaf slug (`etl-run-logging`), not the full path (`monitoring-alerting/etl-run-logging`). The hierarchy is reconstructed from heading levels by `sync-edits-to-xml.py`'s `_infer_paths()`. This is correct and requires no change.

### Anti-Patterns to Avoid
- **Bundling all refs in parent section:** The old pattern. If a ref only appears in a `###` child, it must go in the child's refs, not the parent intro's refs. This is the core problem Phase 21 solves.
- **Generating all content then emitting:** The writer must emit section-by-section as it generates, not accumulate everything and emit at the end. This ensures refs are precisely scoped to the body just written.
- **Using full paths in temp file names:** Slashes in file names cause filesystem errors. Always use the leaf slug for temp file naming.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Nested section placement | Custom state tree manipulation | `write-section.py --parent` flag | Already handles all nesting, overwrite-preservation, error checking |
| Section marker injection | Manual `<!-- section: ... -->` in agent output | `write-section.py` auto-injection (line 186-190) | Already injects markers if missing; duplicating would create double markers |
| Hierarchy reconstruction from flat markers | Custom path inference | `sync-edits-to-xml.py _infer_paths()` | Stack-based heading-level algorithm already handles arbitrary nesting |
| Depth-first assembly | Custom section concatenation | `finalize()` via `_collect_all_sections_depth_first()` | Already walks nested state tree correctly |

**Key insight:** All the machinery for nested emission exists from Phases 18-20. Phase 21 is purely about changing the agent prompts to USE the existing machinery at finer granularity.

## Common Pitfalls

### Pitfall 1: Intro content includes child heading text
**What goes wrong:** When splitting a `##` section into intro + children, the intro accidentally includes the first `###` heading's text.
**Why it happens:** The writer generates the entire section mentally, then tries to split it after the fact.
**How to avoid:** The prompt must instruct: "Write ONLY the text between the `##` heading and the first `###` heading. Stop before the `###` line."
**Warning signs:** Intro body is suspiciously long (>50 lines); duplicate content between intro and first child.

### Pitfall 2: Refs leaking into wrong scope
**What goes wrong:** A typed_ref that's only relevant to a child `###` section gets placed in the parent `##` intro's refs.
**Why it happens:** The writer accumulates all refs for the entire section, then tries to partition them after writing everything.
**How to avoid:** The prompt must instruct: "After writing EACH heading's content, IMMEDIATELY write its refs file with ONLY the refs you just used."
**Warning signs:** Parent intro has refs to symbols only mentioned in child content.

### Pitfall 3: Empty intro body
**What goes wrong:** A `##` section that jumps directly to `###` headings (no intro paragraph) produces an empty content file.
**Why it happens:** Some sections legitimately have no intro text between the `##` heading and the first `###`.
**How to avoid:** The intro must always contain at least the `##` heading line itself (even if no body text follows). The agent should write the `##` heading + `<!-- docs-meta: ... -->` comment as the intro content. write-section.py validates non-empty content.
**Warning signs:** write-section.py exits with "content file is empty" error.

### Pitfall 4: Temp file name collisions
**What goes wrong:** Two different `###` headings across different `##` parents happen to slugify to the same leaf name.
**Why it happens:** Unlikely but possible if template headings repeat (e.g., "Overview" under two different sections).
**How to avoid:** Include the parent slug in the temp file name: `section-devops-OPERATIONS-{parent-slug}-{child-slug}.md`. Or simpler: let the writer generate content sequentially so each temp file is overwritten only after the previous call completes.
**Warning signs:** A section's content unexpectedly matches content from a different parent.

### Pitfall 5: Forgetting --parent on child sections
**What goes wrong:** A `###` heading is emitted without `--parent`, creating a spurious top-level section.
**Why it happens:** The writer prompt doesn't clearly distinguish between `##` calls (no --parent) and `###` calls (with --parent).
**How to avoid:** The prompt must have a clear decision tree: "If this is a `##` heading, omit --parent. If `###`, pass `--parent {##-slug}`. If `####`, pass `--parent {##-slug}/{###-slug}`."
**Warning signs:** Finalize produces more top-level sections than there are `##` headings in the template.

### Pitfall 6: Section markers appearing in wrong position
**What goes wrong:** The `<!-- section: slug -->` marker appears inside the body instead of before the heading.
**Why it happens:** The writer includes the marker in the content file, AND write-section.py injects it again.
**How to avoid:** The prompt should NOT instruct writers to add section markers. write-section.py handles injection automatically (line 186-190). The existing devops-writer.md does not instruct marker injection -- this is correct.
**Warning signs:** Double markers `<!-- section: slug --><!-- section: slug -->` in output.

## Code Examples

### Current devops-writer.md emission pattern (to be changed)
```markdown
# Current step 2g in devops-writer.md:
g. **Write sections and typed references.** For each section you generated, emit it
   through the write-section tool. [...]

   Then for each section, write two temp files and call the script:
   1. Write section content to `{TMP_DIR}/section-devops-{DOCUMENT}-{section-slug}.md`
   2. Write references to `{TMP_DIR}/refs-devops-{DOCUMENT}-{section-slug}.json`
   3. Call:
      python3 {SCRIPTS_DIR}/write-section.py \
        --state-file {TMP_DIR}/write-state-devops.json \
        --document {DOCUMENT} \
        --section {section-slug} \
        --content-file {TMP_DIR}/section-devops-{DOCUMENT}-{section-slug}.md \
        --refs-file {TMP_DIR}/refs-devops-{DOCUMENT}-{section-slug}.json \
        --header-file {TMP_DIR}/header-devops-{DOCUMENT}.md \
        --project-root {project_root}
```

### Target devops-writer.md emission pattern (per-heading)
```markdown
# Target step 2g in devops-writer.md:
g. **Write sections per heading.** For each `##` section, emit its content
   at each heading level through individual write-section calls.

   First, write the document header (once per document, before the first section):
   [... same as current ...]

   Then for each `##` section:

   **Step 1: Emit the intro.** Write ONLY the content between the `##` heading
   and the first `###` heading (or end of section if no `###` exists). This includes
   the `##` heading line, the `<!-- docs-meta: ... -->` comment, and any intro
   paragraphs. Do NOT include `###` heading content.

   1. Write intro to `{TMP_DIR}/section-devops-{DOCUMENT}-{section-slug}.md`
   2. Write refs to `{TMP_DIR}/refs-devops-{DOCUMENT}-{section-slug}.json`
      with ONLY the typed_refs for entities mentioned in the intro
   3. Call:
      python3 {SCRIPTS_DIR}/write-section.py \
        --state-file {TMP_DIR}/write-state-devops.json \
        --document {DOCUMENT} \
        --section {section-slug} \
        --content-file {TMP_DIR}/section-devops-{DOCUMENT}-{section-slug}.md \
        --refs-file {TMP_DIR}/refs-devops-{DOCUMENT}-{section-slug}.json \
        [--header-file ... only on first section] \
        --project-root {project_root}

   **Step 2: Emit each child heading.** For each `###` heading within this section:

   1. Write `###` content to `{TMP_DIR}/section-devops-{DOCUMENT}-{child-slug}.md`
      (the `###` heading line + its body, NOT including any `####` content below it)
   2. Write refs to `{TMP_DIR}/refs-devops-{DOCUMENT}-{child-slug}.json`
      with ONLY the typed_refs for entities mentioned in this `###` body
   3. Call:
      python3 {SCRIPTS_DIR}/write-section.py \
        --state-file {TMP_DIR}/write-state-devops.json \
        --document {DOCUMENT} \
        --section {child-slug} \
        --parent {section-slug} \
        --content-file {TMP_DIR}/section-devops-{DOCUMENT}-{child-slug}.md \
        --refs-file {TMP_DIR}/refs-devops-{DOCUMENT}-{child-slug}.json \
        --project-root {project_root}

   **Step 3: (If `####` headings exist)** For each `####` heading within a `###`:

   [Same pattern with --parent {section-slug}/{child-slug}]
```

### write-section.py --parent CLI usage (from Phase 19, verified)
```bash
# Source: write-section.py argparse, lines 658-661
# Top-level section (no --parent):
python3 write-section.py --state-file STATE --document DOC --section monitoring-alerting \
    --content-file CONTENT --refs-file REFS

# Child section (--parent is the top-level slug):
python3 write-section.py --state-file STATE --document DOC --section etl-run-logging \
    --parent monitoring-alerting \
    --content-file CONTENT --refs-file REFS

# Grandchild (--parent is slash-separated path):
python3 write-section.py --state-file STATE --document DOC --section artifact-format \
    --parent monitoring-alerting/etl-run-logging \
    --content-file CONTENT --refs-file REFS
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One write-section call per `##` | Per-heading calls with `--parent` | Phase 21 (this phase) | Finer-grained refs, better audit convergence |
| Flat sections_order in state | Nested subsections/subsections_order tree | Phase 19 | Enables arbitrary nesting |
| Slug-based section keys | Path-based section keys (slash-separated) | Phase 19-20 | Enables unique identification of nested sections |

**Deprecated/outdated:**
- `get_section_slugs()` in xml_doc.py: Retained as backward-compat alias (Phase 18 decision), but `get_section_paths()` is the current API
- Flat `sections` dict without `subsections` keys: Phase 19 always includes `subsections: {}` and `subsections_order: []`

## Open Questions

1. **Temp file naming for duplicate leaf slugs**
   - What we know: The OPERATIONS template has no duplicate `###` slugs across `##` parents. TROUBLESHOOTING also has no duplicates.
   - What's unclear: Whether the writer might generate duplicate slugs in practice (e.g., two different `##` sections each having a `###` Overview child).
   - Recommendation: Include parent slug in temp file names for safety: `section-devops-OPERATIONS-{parent}-{child}.md`. Low cost, prevents subtle bugs.

2. **Glossary and overview: nesting behavior when no `###` exists**
   - What we know: These templates have only `##` headings. The new emission loop degenerates to the old behavior (one call per `##`, zero child calls).
   - What's unclear: Whether the prompt change should be made anyway for consistency, or left as-is.
   - Recommendation: Update all 3 agents for consistency. The glossary and overview prompts should describe the recursive pattern but note that `###` headings are rare/absent for these document types. This future-proofs them if templates evolve.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via uv run) |
| Config file | pyproject.toml |
| Quick run command | `uv run pytest auto-doc/scripts/tests/test_write_section.py -x --tb=short -q --no-header` |
| Full suite command | `uv run pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WHE-01 | Per-heading write-section calls with --parent | unit | `uv run pytest auto-doc/scripts/tests/test_write_section.py::TestNestedSectionWrite -x --tb=short -q --no-header` | Existing (Phase 19 tests cover --parent mechanics) |
| WHE-02 | Only 3 writers updated | manual-only | Visual diff of agent files | N/A - prompt-only change, verified by code review |
| WHE-03 | Markdown output identical | integration | `uv run pytest auto-doc/scripts/tests/test_write_section.py::TestNestedFinalize::test_nested_finalize_markdown_assembly -x --tb=short -q --no-header` | Existing |
| WHE-04 | Section markers at every heading level | unit | `uv run pytest auto-doc/scripts/tests/test_write_section.py -x --tb=short -q --no-header -k "marker"` | Existing (marker injection is in write-section.py, already tested) |
| WHE-05 | Refs match body precisely | integration | New test needed: verify that nested state tree has refs only in correct scopes | Wave 0 |
| WHE-06 | End-to-end round-trip fidelity | integration | New test needed: build nested state -> finalize -> assemble -> sync-edits -> verify paths match | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest auto-doc/scripts/tests/test_write_section.py -x --tb=short -q --no-header`
- **Per wave merge:** `uv run pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `auto-doc/scripts/tests/test_write_section.py::TestPerHeadingEmission` -- new test class covering WHE-05 (refs scoped to correct body) and WHE-06 (round-trip build->finalize->assemble->sync)
- [ ] No new test files needed -- extend existing test_write_section.py with new test class

## Sources

### Primary (HIGH confidence)
- `auto-doc/scripts/write-section.py` -- read in full, verified --parent flag, marker injection, nested state tree handling
- `auto-doc/scripts/assemble-markdown.py` -- verified walk_sections depth-first assembly
- `auto-doc/scripts/sync-edits-to-xml.py` -- verified _infer_paths heading-level reconstruction
- `auto-doc/agents/devops-writer.md` -- read in full, current emission pattern documented
- `auto-doc/agents/glossary-writer.md` -- read in full, current emission pattern documented
- `auto-doc/agents/overview-writer.md` -- read in full, current emission pattern documented
- `auto-doc/references/templates/devops/OPERATIONS.template.md` -- verified heading structure (7 `##` sections, ~15 `###` headings)
- `auto-doc/references/templates/devops/TROUBLESHOOTING.template.md` -- verified heading structure (6 `##` sections, ~12 `###` headings)
- `auto-doc/references/templates/GLOSSARY.template.md` -- verified `##`-only structure
- `auto-doc/references/templates/OVERVIEW.template.md` -- verified `##`-only structure
- `auto-doc/scripts/tests/test_write_section.py` -- 51 tests passing, covers nested state, finalize, merge, parse

### Secondary (MEDIUM confidence)
- `auto-doc/commands/auto-doc-generate.md` -- verified writer spawning pattern and finalize flow

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all scripts verified by reading source, all tests passing
- Architecture: HIGH -- patterns derived from existing working code and test coverage
- Pitfalls: HIGH -- identified from code analysis of write-section.py edge cases and template structures

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (stable -- all infrastructure is internal to this project)
