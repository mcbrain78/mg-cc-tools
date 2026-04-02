# Phase 22: Heading Iterator Script - Research

**Researched:** 2026-04-02
**Domain:** Python CLI script, template parsing, state machine, JSON I/O
**Confidence:** HIGH

## Summary

Phase 22 creates `next-heading.py`, a script-gated heading iterator that the writer agent calls in a loop. On each call it returns one of three JSON response types: orient (at `##` section boundaries with source files and heading outline), write (for each heading with PURPOSE, EXAMPLE, and heading_path), or done. The script parses a refined template on first invocation, persists state to a JSON file, and resumes from persisted state on subsequent calls.

This script follows the proven `next-section.py` pattern from the verify pipeline -- same state machine mechanic where the script controls ordering and the LLM controls actions. The key differences are: (a) two response types instead of one (orient + write vs just section), (b) template parsing with HTML comment extraction instead of manifest reading, and (c) depth-first traversal through a heading tree rather than a flat section list.

All infrastructure is already in place: `lib/json_io.py` for atomic JSON I/O, `slugify_heading()` in `write-section.py` for slug generation, the `source_material_index` structure in `docs-scan.json` for source file lookups, and the `--section`/`--parent` convention in `write-section.py` for heading_path compatibility. The refined template format uses `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` multi-line HTML comments which the parser must extract.

**Primary recommendation:** Implement next-heading.py as a single-file script following next-section.py's pattern with: (1) template parser that extracts heading tree with PURPOSE/EXAMPLE, (2) depth-first traversal emitting orient at `##` boundaries, write for each heading, and done at end, (3) source file lookup from scan file's `source_material_index`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- 4 required arguments: `--state-file`, `--template`, `--scan-file`, `--document`
- State file path: `.mg/docs/tmp/heading-state-{audience}.json` -- persists parsed template state between calls
- Template path: `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` -- the refined template to parse
- Scan file: `.mg/docs/docs-scan.json` -- source of `source_material_index` for source file lookups
- Document: the document identifier (e.g., OPERATIONS) used as key prefix in `source_material_index`
- On first invocation, parse the refined template: extract heading tree, `<!-- PURPOSE: ... -->` comment, and `<!-- EXAMPLE: ... -->` block per heading
- Look up source files from `source_material_index` in scan file using `{DOCUMENT}/{section-slug}` keys (## section slugs only)
- Persist all parsed state to `--state-file` as JSON for subsequent calls
- Subsequent calls read state from the state file -- no re-parsing
- Orient response (emitted at each `##` section boundary): `{"type": "orient", "section": "{slug}", "heading_outline": ["{slug}", "{slug}/{child-slug}", ...], "source_files": [...]}`
- Write response (emitted for every heading including `##` itself): `{"type": "write", "heading_path": "{slug}/{child-slug}", "level": 3, "purpose": "...", "example": "...", "parent_path": "{slug}"}`
- Done response (emitted after all headings processed): `{"done": true, "headings_processed": N}`
- Depth-first traversal through the heading tree
- Orient emitted at each `##` section boundary -- before any writes for that section
- Write emitted for every heading: the `##` heading itself first, then its `###` children depth-first, then `####` grandchildren
- For `##`-level write responses, `parent_path` is omitted (no parent)
- Sequence: orient -> write x N -> orient -> write x N -> ... -> done
- Source files are grouped at `##` granularity -- looked up from `source_material_index` using `{DOCUMENT}/{section-slug}` keys
- Orient response carries the source file list for the entire `##` section
- Write responses do NOT include source files
- heading_path: slash-separated path `{section-slug}/{child-slug}/{grandchild-slug}`
- Maps to write-section.py: last segment -> `--section`, everything before -> `--parent`
- For `##`-level headings (no `/` in path), `--parent` is omitted
- Follow the proven `next-section.py` pattern from the verify pipeline

### Claude's Discretion
- Internal data structures for heading tree representation (list of dicts, tree of nodes, etc.)
- State file JSON schema -- the internal format of the persisted state
- Error handling: malformed templates, missing scan data, missing source_material_index keys
- Exact parsing strategy for `<!-- PURPOSE: -->` and `<!-- EXAMPLE: -->` HTML comments (regex, html.parser, line-by-line)
- Whether to validate the refined template's `<!-- REFINED: -->` metadata or just pass it through
- Test fixture design and structure

### Deferred Ideas (OUT OF SCOPE)
- Parallel heading writes -- sibling headings could be parallelized since they share source context, but sequential loop is simpler and sufficient
- Per-heading source file assignment -- source files stay at `##` granularity; splitting to `###` would require refiner changes
- Merge mode for refined templates -- overwrite only
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HIT-01 | Script accepts four required arguments (`--state-file`, `--template`, `--scan-file`, `--document`) | Standard argparse with `required=True`, matches existing next-section.py CLI pattern |
| HIT-02 | First call parses refined template and extracts heading tree with PURPOSE and EXAMPLE content (multi-line HTML comments); subsequent calls resume from persisted state | Template parser extracts heading hierarchy using regex for `##`-`####` headings and `<!-- PURPOSE: -->` / `<!-- EXAMPLE: -->` comments; state persisted via `lib/json_io.save_json` |
| HIT-03 | Orient JSON response at each `##` section boundary with section slug, slug-only heading outline, source files from scan file's `source_material_index` | Source files looked up via `{DOCUMENT}/{section-slug}` key in `source_material_index`; heading_outline is flattened depth-first list of heading_paths for that section |
| HIT-04 | Write JSON response for every heading with heading_path, level, purpose, example; `##`-level writes omit parent_path | heading_path uses slash-separated slug convention; level is the markdown heading level (2, 3, 4) |
| HIT-05 | Done JSON response after all headings processed with headings_processed count | Mirrors next-section.py done response pattern |
| HIT-06 | Depth-first ordering: orient then writes per `##` section, source files only in orient | State machine tracks section_index and heading_index within each section for depth-first traversal |
| HIT-07 | heading_path slug convention: last segment maps to `--section`, preceding segments to `--parent` | Validated against write-section.py's `_resolve_parent()` which walks slash-separated paths |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lib/json_io.py | Existing | Atomic JSON load/save for state persistence | Already used by all pipeline scripts; provides `load_json(path, default)` and `save_json(path, data)` |
| argparse | stdlib | CLI argument parsing | Standard for all auto-doc scripts |
| re | stdlib | Regex-based template parsing | Sufficient for HTML comment extraction; no external parser needed |
| json | stdlib | JSON serialization for stdout responses | Standard stdout communication protocol |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| os, sys | stdlib | Path operations, stderr output, sys.path insert | Standard script infrastructure |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Regex parsing | html.parser | html.parser handles nested tags but `<!-- COMMENT -->` extraction is simpler with regex; templates are well-structured, not arbitrary HTML |
| Flat list of heading dicts | Tree of node objects | Flat list is simpler for depth-first iteration; tree structure adds complexity without benefit since traversal order is just sequential iteration |

**Installation:**
No new dependencies needed. All imports are stdlib + existing lib/json_io.py.

## Architecture Patterns

### Recommended Project Structure
```
auto-doc/scripts/
   next-heading.py           # New script (this phase)
   next-section.py            # Existing pattern to follow
   lib/json_io.py             # Shared I/O utilities
auto-doc/scripts/tests/
   test_next_heading.py       # New test file (this phase)
```

### Pattern 1: Script-Gated State Machine (from next-section.py)
**What:** Python script that the LLM calls in a loop. Each call returns one JSON response and advances internal state. State persists in a JSON file between calls.
**When to use:** When the LLM must process items one at a time without reading ahead.
**Example (from next-section.py):**
```python
# Load or initialize state
state = load_json(args.state_file)
if state is None:
    state = init_state(...)

# Check if done
if index >= len(items):
    print(json.dumps({"done": True, ...}))
    return

# Emit current item
item = items[index]
state["index"] = index + 1
save_json(args.state_file, state)
print(json.dumps({"done": False, ...}))
```

### Pattern 2: Two-Phase Response Cycle (orient + write)
**What:** At each `##` section boundary, emit an orient response first (source files + heading outline), then emit write responses for each heading in depth-first order. The writer uses orient to load source context, then processes writes one at a time.
**When to use:** When the consumer needs to prepare context (read files) before processing individual items.
**Tracking approach:** State tracks two indices: `section_index` (which `##` section) and `heading_index` (which heading within the current section's depth-first list). A `needs_orient` flag indicates whether the next call should emit orient or write.

### Pattern 3: Template Parsing with HTML Comment Extraction
**What:** Parse refined templates by splitting on `##`-`####` headings and extracting `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` multi-line HTML comments per heading.
**When to use:** First call only, when no state file exists.
**Key parsing challenge:** Comments can span multiple lines. The `<!-- EXAMPLE: -->` blocks contain full markdown including headings, code blocks, and tables -- so the parser must match the comment delimiters (`<!--` and `-->`) rather than trying to parse the content.

### Anti-Patterns to Avoid
- **Re-parsing on every call:** The template must be parsed once and state persisted. Re-parsing wastes time and could produce different results if the template changes mid-loop.
- **Including source files in write responses:** Source files belong only in orient. The writer already loaded them during orient.
- **Breadth-first ordering:** The spec requires depth-first: `##` heading, then all its `###` children (each with their `####` grandchildren) before moving to the next `##`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic JSON writes | Manual file.write | `lib/json_io.save_json()` | Handles temp file + os.replace, dir creation |
| Slug generation | Custom slugify | Copy `slugify_heading()` from write-section.py | Identical algorithm needed for heading_path compatibility |
| JSON stdout protocol | Custom formatting | `json.dumps()` + `print()` | Matches all other pipeline scripts |

**Key insight:** The slugify function MUST match write-section.py's `slugify_heading()` exactly. If the two produce different slugs for the same heading text, the heading_path from next-heading.py won't match write-section.py's expectations. Copy the function or (better) extract it to a shared lib module.

## Common Pitfalls

### Pitfall 1: Slug Mismatch Between next-heading.py and write-section.py
**What goes wrong:** next-heading.py generates slugs using a different algorithm than write-section.py, causing `--section` and `--parent` arguments to not match existing state entries.
**Why it happens:** Multiple copies of slugify exist (write-section.py, list-optional-sections.py, prepare-doc-review.py) with slightly different names and potentially different behavior.
**How to avoid:** Copy `slugify_heading()` verbatim from write-section.py OR (recommended) extract to `lib/slugify.py` as a shared utility. Test slug output against write-section.py for the same input headings.
**Warning signs:** Tests pass in isolation but integration fails with "parent section not found" errors.

### Pitfall 2: Multi-Line HTML Comment Parsing
**What goes wrong:** PURPOSE or EXAMPLE comment extraction fails when comments span many lines and contain markdown headings, code blocks, or nested `<!--` markers.
**Why it happens:** Naive regex like `<!--\s*PURPOSE:\s*(.*?)-->` with `re.DOTALL` works for single-line but can be greedy or fail to match nested structures.
**How to avoid:** Use a two-step approach: (1) find `<!-- PURPOSE:` start marker, (2) find the matching `-->` end marker. The EXAMPLE blocks can contain `###`/`####` headings inside them -- the parser must not confuse these with actual template headings.
**Warning signs:** Parsed heading tree has wrong hierarchy; EXAMPLE content is truncated or includes the next heading.

### Pitfall 3: Headings Inside EXAMPLE Blocks
**What goes wrong:** The parser splits the template on `##`-`####` headings and accidentally picks up headings that are inside `<!-- EXAMPLE: ... -->` comment blocks as real template headings.
**How to avoid:** Strip HTML comments BEFORE splitting on headings, OR parse sequentially: for each `##`-`####` heading found at the top level (not inside a comment), extract its PURPOSE and EXAMPLE comments from the content between it and the next top-level heading.
**Warning signs:** The heading tree has many more entries than expected; heading text includes example content.

### Pitfall 4: Missing source_material_index Keys
**What goes wrong:** The scan file doesn't have a `{DOCUMENT}/{section-slug}` key for every `##` section (e.g., section was added by the refiner but not yet scanned).
**Why it happens:** Refined templates can add sections that didn't exist in the original scan.
**How to avoid:** Return empty `source_files: []` for missing keys rather than raising an error. Print a warning to stderr. The writer will handle sections with no source files gracefully.
**Warning signs:** Script crashes on a legitimate template because the scan is stale.

### Pitfall 5: Orient vs Write Index Tracking
**What goes wrong:** After an orient response, the next call incorrectly re-emits orient or skips the first write.
**Why it happens:** Complex state with two indices (section_index, heading_index) and a needs_orient flag.
**How to avoid:** Use a simple flat approach: build the complete emission sequence (orient, write, write, ..., orient, write, ..., done) during parsing and store it as a list. Each call just pops the next item. No complex index tracking needed.
**Warning signs:** Orient is emitted twice in a row, or the `##` write is skipped after orient.

### Pitfall 6: OPTIONAL Sections in Refined Templates
**What goes wrong:** The parser includes `<!-- OPTIONAL -- delete if not applicable -->` sections that the refiner was supposed to remove.
**Why it happens:** Refined templates produced by Phase 23 should have already resolved optional sections, but the parser might encounter them in generic templates during testing.
**How to avoid:** next-heading.py should include all headings found in the template regardless of OPTIONAL markers. The refined template is the writer's sole structural input -- if a heading is present, it should be written. OPTIONAL filtering is the refiner's job.
**Warning signs:** Sections that should be skipped appear in the heading queue.

## Code Examples

### Template Parsing: Extract Headings with PURPOSE/EXAMPLE
```python
# Recommended parsing approach:
# 1. Find all top-level headings (##, ###, ####) NOT inside HTML comments
# 2. For each heading, extract PURPOSE and EXAMPLE from the content after it

import re

def parse_template(template_text):
    """Parse a refined template into a heading tree.

    Returns:
        List of section dicts, each with:
        - slug: str
        - level: int (2, 3, 4)
        - title: str (original heading text)
        - purpose: str (extracted from <!-- PURPOSE: ... -->)
        - example: str (extracted from <!-- EXAMPLE: ... -->)
        - children: list of child heading dicts
    """
    # Step 1: Strip all HTML comments to get raw heading structure,
    #         but save comment content keyed by position for extraction
    # Step 2: Split on headings, extract comments per heading block
    ...
```

### Depth-First Emission Sequence (Flat List Approach)
```python
def build_emission_queue(sections, document, source_material_index):
    """Build the complete sequence of responses to emit.

    Returns:
        List of dicts, each either an orient, write, or done response.
    """
    queue = []
    total_headings = 0

    for section in sections:
        # Orient response for this ## section
        slug = section["slug"]
        key = f"{document}/{slug}"
        source_files = source_material_index.get(key, {}).get("source_files", [])

        # Collect all heading paths depth-first for outline
        outline = collect_heading_paths(section)

        queue.append({
            "type": "orient",
            "section": slug,
            "heading_outline": outline,
            "source_files": source_files,
        })

        # Write responses for each heading depth-first
        for heading in walk_headings_depth_first(section):
            total_headings += 1
            response = {
                "type": "write",
                "heading_path": heading["path"],
                "level": heading["level"],
                "purpose": heading["purpose"],
                "example": heading["example"],
            }
            if "/" in heading["path"]:
                response["parent_path"] = heading["path"].rsplit("/", 1)[0]
            queue.append(response)

    queue.append({"done": True, "headings_processed": total_headings})
    return queue
```

### State File Schema
```json
{
  "queue": [
    {"type": "orient", "section": "infrastructure-overview", "heading_outline": ["infrastructure-overview", "infrastructure-overview/deployment-topology", "infrastructure-overview/external-dependencies"], "source_files": ["src/config.py"]},
    {"type": "write", "heading_path": "infrastructure-overview", "level": 2, "purpose": "...", "example": "..."},
    {"type": "write", "heading_path": "infrastructure-overview/deployment-topology", "level": 3, "purpose": "...", "example": "...", "parent_path": "infrastructure-overview"},
    {"type": "write", "heading_path": "infrastructure-overview/external-dependencies", "level": 3, "purpose": "...", "example": "...", "parent_path": "infrastructure-overview"},
    {"type": "orient", "section": "deployment", ...},
    ...
    {"done": true, "headings_processed": 15}
  ],
  "index": 0
}
```

### Main Function Pattern (Following next-section.py)
```python
def main():
    parser = argparse.ArgumentParser(...)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--scan-file", required=True)
    parser.add_argument("--document", required=True)
    args = parser.parse_args()

    state = load_json(args.state_file)
    if state is None:
        state = init_state(args.template, args.scan_file, args.document)

    queue = state["queue"]
    index = state["index"]

    # Emit next response
    response = queue[index]

    # Advance index
    state["index"] = index + 1
    save_json(args.state_file, state)

    # Print JSON to stdout
    print(json.dumps(response))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Writer reads full template, decides own sections | Script feeds headings one at a time | Phase 22 (new) | Writer becomes stateless per heading; structure controlled by template |
| Source files fetched per heading by writer | Source files grouped at `##` level by iterator | Phase 22 (new) | Reduces redundant source reads; orient/write separation |
| Writer uses existing next-section.py (verify only) | New next-heading.py for generate pipeline | Phase 22 (new) | Different response types (orient+write vs section-only) |

**Deprecated/outdated:**
- Direct template reading by writer agents (will be replaced by next-heading.py loop in Phase 24)

## Open Questions

1. **Should slugify_heading be extracted to lib/?**
   - What we know: The function exists in write-section.py, list-optional-sections.py, and prepare-doc-review.py with slightly different names
   - What's unclear: Whether to duplicate it in next-heading.py or extract to shared lib
   - Recommendation: Copy `slugify_heading()` verbatim from write-section.py for now. Extraction to lib is a refactoring concern, not a correctness concern. The critical thing is identical behavior.

2. **How to handle refined template header content (lines before first ## heading)?**
   - What we know: Templates have `<!-- DIATAXIS: ... -->`, `<!-- AUDIENCE: ... -->`, `# Title`, and `<!-- docs-meta: ... -->` before the first `##`
   - What's unclear: Whether the parser should preserve or discard this preamble
   - Recommendation: Discard. next-heading.py only needs the heading tree. The writer agent handles document headers separately via write-section.py's `--header-file`.

3. **Behavior when template file doesn't exist?**
   - What we know: Phase 23 creates refined templates; Phase 24 uses them via next-heading.py
   - What's unclear: Whether next-heading.py should error or produce a meaningful message
   - Recommendation: Exit 1 with clear error message to stderr (matching next-section.py's pattern for missing manifest).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | pyproject.toml (existing) |
| Quick run command | `pytest auto-doc/scripts/tests/test_next_heading.py --tb=short -q --no-header` |
| Full suite command | `pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HIT-01 | Four required CLI arguments | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestCLI -x` | Wave 0 |
| HIT-02 | Template parsing + state persistence | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestTemplateParsing -x` | Wave 0 |
| HIT-03 | Orient response with source files | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestOrientResponse -x` | Wave 0 |
| HIT-04 | Write response with heading_path, level, purpose, example | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestWriteResponse -x` | Wave 0 |
| HIT-05 | Done response with headings_processed count | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestDoneResponse -x` | Wave 0 |
| HIT-06 | Depth-first ordering, source files only in orient | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestDepthFirstOrdering -x` | Wave 0 |
| HIT-07 | heading_path to write-section.py argument mapping | unit | `pytest auto-doc/scripts/tests/test_next_heading.py::TestHeadingPathConvention -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest auto-doc/scripts/tests/test_next_heading.py --tb=short -q --no-header`
- **Per wave merge:** `pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `auto-doc/scripts/tests/test_next_heading.py` -- covers HIT-01 through HIT-07
- [ ] `auto-doc/scripts/next-heading.py` -- the script itself

*(No framework gaps -- existing test infrastructure covers all needs)*

## Sources

### Primary (HIGH confidence)
- `auto-doc/scripts/next-section.py` -- direct architectural reference, read in full
- `auto-doc/scripts/write-section.py` -- integration contract (slugify_heading, --section, --parent), read in full
- `auto-doc/scripts/lib/json_io.py` -- shared I/O utilities, read in full
- `auto-doc/references/schema.md` -- source_material_index schema definition
- `auto-doc/references/templates/devops/OPERATIONS.template.md` -- representative template format with PURPOSE/EXAMPLE
- `auto-doc/references/templates/devops/TROUBLESHOOTING.template.md` -- template with nested ### headings in EXAMPLE blocks
- `auto-doc/references/templates/GLOSSARY.template.md` -- simpler template format (no ### children)
- `auto-doc/agents/devops-writer.md` -- downstream consumer, per-heading emission pattern
- `.planning/phases/24-writer-orient-write-integration/24-CONTEXT.md` -- downstream Phase 24 integration requirements
- `auto-doc/scripts/tests/test_next_section.py` -- test pattern to follow

### Secondary (MEDIUM confidence)
- `.planning/phases/21-writer-agent-per-heading-emission/21-RESEARCH.md` -- prior phase context

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all components are existing stdlib + lib/json_io.py, no new dependencies
- Architecture: HIGH - next-section.py provides a proven, working pattern; differences are well-understood
- Pitfalls: HIGH - identified from reading actual template content and existing parser implementations

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable -- no external dependency changes expected)
