# Phase 19: Nested Write-Section & Assembly - Research

**Researched:** 2026-04-01
**Domain:** write-section.py nested state format, --parent CLI flag, recursive XML finalize, assemble-markdown.py depth-first concatenation
**Confidence:** HIGH

## Summary

Phase 19 extends write-section.py and assemble-markdown.py to support hierarchical section emission. The Phase 18 foundation (recursive xml_doc.py) is already complete -- all XML build/parse/serialize/navigate/mutate functions support arbitrary nesting. This phase bridges the gap between the flat state format used by write-section.py and the nested XML model by introducing a `--parent` flag on section-write mode, a recursive state format with `subsections`/`subsections_order` at every level, finalize logic that builds nested XML from the nested state, and a recursive depth-first concatenation in assemble-markdown.py.

The scope is confined to two scripts: write-section.py (section_write, finalize, parse_existing_sections, CLI args) and assemble-markdown.py (assemble function). No agent prompts, command files, or downstream pipeline scripts change -- those are Phases 20 and 21. The clean-cutover decision (no dual-format state) simplifies implementation: the state format changes shape, and old state files are not migrated.

The key technical challenge is the state tree traversal in `section_write()`: given a `--parent` path like `monitoring-alerting/health-artifact`, the function must walk the state tree to find the parent section's `subsections` dict, creating intermediate `subsections`/`subsections_order` keys if absent, then insert the new section. The finalize function must recursively walk this state tree to build nested `<section>` XML elements using xml_doc.py's `build_xml_doc`. The merge mode must be updated to split on all heading levels (not just `##`) and reconstruct the tree from heading depth. assemble-markdown.py must recursively concatenate bodies depth-first using `walk_sections` from xml_doc.py.

**Primary recommendation:** Implement in two plans: (1) write-section.py changes (--parent flag, nested state, finalize, merge mode) with tests, (2) assemble-markdown.py recursive concatenation with tests.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- New `--parent` flag on write-section.py specifies where in the tree to insert a child section
- `--parent` omitted -> top-level section (appended to `sections_order`, same as today)
- `--parent` is a slug -> child of that top-level section
- `--parent` is a slash-separated path -> child at the resolved tree position (e.g., `monitoring-alerting/health-artifact`)
- Parent must exist before child is emitted -- writer processes depth-first: heading intro first, then each child heading in order
- Sections gain `subsections` (dict) and `subsections_order` (list) keys for child sections
- `subsections` maps slug -> child section dict (same shape: `content`, `typed_refs`, `subsections`, `subsections_order`)
- Tree is arbitrarily deep -- same recursive structure at every level
- `section_write()` traverses the state tree using the parent path, creates `subsections`/`subsections_order` at the resolved parent if they don't exist, then inserts the new section
- Finalize recursively builds nested `<section>` XML elements from the state tree
- Each section in the state tree becomes a `<section>` XML element with its own `<refs>` and `<body>`
- Child sections are nested inside their parent `<section>` element
- Uses xml_doc.py functions from Phase 18 for XML construction
- `--merge` flag and `parse_existing_sections()` updated for nested sections -- not removed (D4 note)
- Merge mode splits on all heading levels (not just `##`), matches by path
- This is the update pipeline path for incremental section updates
- assemble-markdown.py: Recursive depth-first concatenation: section body, then child section bodies in order
- Output is the same flat markdown as today -- nesting only affects how sections are stored/tracked, not the assembled output
- Clean cutover -- no dual-format state handling (D4)
- Old flat state files are not migrated; new generation runs produce nested state from scratch

### Claude's Discretion
- Error handling when `--parent` references a non-existent parent path
- Whether finalize validates tree integrity (e.g., orphaned sections) before building XML
- Internal implementation of state tree traversal in `section_write()`
- How `parse_existing_sections()` reconstructs the tree from heading levels during merge

### Deferred Ideas (OUT OF SCOPE)
- Downstream pipeline script updates (verify, extract, merge, sync, prepare, load-audit) -- Phase 20
- Writer agent prompt changes for per-heading emission -- Phase 21
- Stale writer modernization -- separate effort
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WSA-01 | write-section.py accepts `--parent` flag placing sections at any tree depth | New `--parent` argparse argument; `section_write()` traverses state tree to resolved parent, inserts at correct level |
| WSA-02 | Parent section must exist before child can be emitted | State tree traversal validates parent path exists; exits with error if parent slug not found at any segment |
| WSA-03 | Finalize produces nested `<section>` XML with per-section `<refs>` and `<body>` | Recursive state-to-sections converter builds section dicts with `children` key; passes to `build_xml_doc` from xml_doc.py |
| WSA-04 | Merge mode supports nested sections, splits all heading levels, matches by path | `parse_existing_sections()` rewritten to split on `##`-`#####` headings, infer depth, reconstruct tree; merge matches by slash-separated path |
| WSA-05 | assemble-markdown.py performs recursive depth-first concatenation | Uses `walk_sections` from xml_doc.py (already yields depth-first); collect bodies in order |
| WSA-06 | Assembled markdown output remains flat | `walk_sections` yields every section body in document order; join with `\n\n` same as today |
| WSA-07 | Clean cutover: old flat state files not migrated or supported | No state migration code; new `section_write()` always produces nested format with `subsections`/`subsections_order` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lxml | (existing) | XML tree manipulation via xml_doc.py | Already used; Phase 18 built recursive build/parse/serialize |
| argparse | stdlib | CLI argument parsing | Already used in both scripts |
| json | stdlib | State file I/O | Already used via lib/json_io.py |
| re | stdlib | Heading-level detection in parse_existing_sections | Already used for `## ` splitting |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| lib/xml_doc.py | Phase 18 | `build_xml_doc`, `walk_sections`, `add_section`, `update_section_body`, `update_section_refs`, `get_section_slugs`, `get_section_paths` | Finalize XML construction and assemble-markdown.py |
| lib/json_io.py | existing | `load_json`, `save_json`, `save_text` | Atomic state file and output writes |
| pytest | existing | Test framework | All tests |

### No New Dependencies
This phase adds no new libraries. All changes use existing imports plus xml_doc.py functions from Phase 18.

## Architecture Patterns

### State Tree Structure (Nested Format)

The state file gains recursive nesting. Each section dict gains `subsections` and `subsections_order`:

```json
{
  "documents": {
    "OPS": {
      "header": "...",
      "sections_order": ["monitoring-alerting", "deployment"],
      "sections": {
        "monitoring-alerting": {
          "content": "<!-- section: monitoring-alerting -->\n## Monitoring & Alerting\n\nIntro text...",
          "symbols": [...],
          "file_paths": [...],
          "typed_refs": [...],
          "subsections": {
            "etl-run-logging": {
              "content": "<!-- section: etl-run-logging -->\n### ETL Run Logging\n\nLogs...",
              "symbols": [...],
              "file_paths": [...],
              "typed_refs": [...],
              "subsections": {},
              "subsections_order": []
            }
          },
          "subsections_order": ["etl-run-logging"]
        },
        "deployment": {
          "content": "...",
          "symbols": [...],
          "file_paths": [...],
          "typed_refs": [...],
          "subsections": {},
          "subsections_order": []
        }
      }
    }
  }
}
```

### Pattern 1: State Tree Traversal for --parent Resolution

**What:** `section_write()` resolves a `--parent` path by walking the state tree segment by segment.
**When to use:** Every `section_write()` call with `--parent` set.

```python
def _resolve_parent(doc, parent_path):
    """Walk the state tree to find the parent section dict.

    Args:
        doc: Document dict from state (has sections, sections_order).
        parent_path: Slash-separated path (e.g., "monitoring-alerting/health-artifact").

    Returns:
        The parent section dict (which has subsections/subsections_order).

    Raises:
        SystemExit: If any path segment doesn't exist.
    """
    segments = parent_path.split("/")

    # First segment must be in top-level sections
    current = doc["sections"].get(segments[0])
    if current is None:
        print(f"Error: parent section not found: {segments[0]}", file=sys.stderr)
        sys.exit(1)

    # Walk remaining segments through subsections
    for i, seg in enumerate(segments[1:], 1):
        subs = current.get("subsections", {})
        current = subs.get(seg)
        if current is None:
            path_so_far = "/".join(segments[:i+1])
            print(f"Error: parent section not found: {path_so_far}", file=sys.stderr)
            sys.exit(1)

    return current
```

### Pattern 2: Recursive State-to-XML Conversion for Finalize

**What:** Convert the nested state tree into the section dict format expected by `build_xml_doc`.
**When to use:** During finalize, before calling `build_xml_doc`.

```python
def _state_section_to_xml_section(slug, section_data):
    """Convert a state section dict to the format expected by build_xml_doc.

    Returns:
        Dict with slug, body, and children keys.
    """
    children = []
    for child_slug in section_data.get("subsections_order", []):
        child_data = section_data.get("subsections", {}).get(child_slug)
        if child_data:
            children.append(_state_section_to_xml_section(child_slug, child_data))

    return {
        "slug": slug,
        "body": section_data["content"],
        "children": children,
    }
```

### Pattern 3: Heading-Level-Aware Parsing for Merge Mode

**What:** `parse_existing_sections()` splits on all heading levels and reconstructs a tree.
**When to use:** During merge mode finalize when reading existing documents.

```python
def parse_existing_sections(content):
    """Parse markdown into header + nested section tree.

    Splits on ## through ##### headings. Each heading's level determines
    its depth in the tree. Returns tree structure matching state format.

    Returns:
        (header_text, tree_sections)
        where tree_sections is a list of (slug, heading_line, body, children) tuples.
    """
    # Split on any heading level ## through #####
    parts = re.split(r"(?=^#{2,5} )", content, flags=re.MULTILINE)
    # Count '#' characters to determine depth
    # ## = depth 0 (top-level), ### = depth 1, #### = depth 2, ##### = depth 3
    # Build tree using a stack
```

### Pattern 4: Depth-First Assembly via walk_sections

**What:** assemble-markdown.py uses `walk_sections` to iterate all sections depth-first.
**When to use:** In the `assemble()` function.

```python
from lib.xml_doc import parse_xml_doc, walk_sections

def assemble(xml_path):
    doc = parse_xml_doc(xml_path)
    parts = []
    header = doc["meta"]["header"]
    if header:
        parts.append(header.rstrip("\n"))

    for path, section in walk_sections(doc["sections"]):
        body = section["body"]
        if body:
            parts.append(body.strip("\n"))

    return "\n\n".join(parts) + "\n"
```

### Anti-Patterns to Avoid
- **Flattening state for finalize:** Do NOT flatten the nested state back to a flat list and call the old finalize. Build the nested sections_for_xml list that includes children, and pass to `build_xml_doc` which already handles recursion.
- **Global slug uniqueness in state:** Slugs must be unique among siblings only, not globally. The state tree naturally enforces this since each level has its own `subsections` dict.
- **Modifying xml_doc.py:** Phase 18 already built all needed functions. This phase only modifies write-section.py and assemble-markdown.py.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Nested XML construction | Custom etree.SubElement loops | `build_xml_doc(sections=[...with children...])` from xml_doc.py | Already recursive, tested at 3 levels deep in Phase 18 |
| Depth-first iteration over XML sections | Manual recursive traversal of parsed XML | `walk_sections(doc["sections"])` from xml_doc.py | Already yields (path, section_dict) in correct order |
| Section path resolution in XML | Custom path walker for XML elements | `_find_section_by_path`, `add_section(parent_path=...)` from xml_doc.py | Path-based navigation already implemented |
| Atomic file writes | Manual temp-file + os.replace | `save_json()`, `save_text()` from lib/json_io.py | Established atomic I/O pattern |
| XML ref construction | Manual etree ref building | `update_section_refs(tree, path, flat_refs)` from xml_doc.py | Already handles all ref types with path addressing |

**Key insight:** Phase 18 did the hard work of recursive XML. This phase only needs to (1) add a tree traversal to the JSON state format and (2) convert state tree into the section dict format xml_doc.py already consumes.

## Common Pitfalls

### Pitfall 1: Manifest Generation Must Walk the Full Tree
**What goes wrong:** The finalize manifest builder iterates only `sections_order` and `sections` (flat). With nesting, symbols/file_paths in child sections would be omitted from the manifest.
**Why it happens:** The existing manifest code loops over `doc_data.get("sections_order", [])` and `sections.get(section_slug, {})` at one level only.
**How to avoid:** Walk the full nested state tree recursively when building manifest entries. Each section at any depth with non-empty symbols or file_paths gets an entry. Use slash-separated paths as manifest keys (e.g., `"monitoring-alerting/etl-run-logging"`).
**Warning signs:** Tests that check manifest contents for nested sections find missing entries.

### Pitfall 2: _written_sections Must List All Paths
**What goes wrong:** The `_written_sections.sections_written` list only contains top-level slugs. Downstream consumers expect all written section paths.
**Why it happens:** Current code does `list(sections_order)` which is top-level only.
**How to avoid:** Collect all section paths recursively from the state tree for `sections_written`.
**Warning signs:** `sections_written` list shorter than total section count.

### Pitfall 3: Merge Mode Heading-Level Detection Must Be Robust
**What goes wrong:** `parse_existing_sections()` currently splits on `## ` only. With nested sections, `### ` and deeper headings in existing documents must also be parsed.
**Why it happens:** The regex `r"(?=^## )"` only matches level-2 headings.
**How to avoid:** Use `r"(?=^#{2,5} )"` to split on headings at all relevant levels. Count the `#` characters to determine depth. Build a tree from the flat list using a stack-based algorithm.
**Warning signs:** Merge mode silently discards `###` content or merges at wrong depth.

### Pitfall 4: XML Merge Mode Must Use Path-Based Lookup
**What goes wrong:** The XML merge code in finalize uses `get_section_slugs(tree)` for existing slug lookup, then `add_section(tree, slug, body)` for new sections. With nesting, this misses child sections and doesn't place new children correctly.
**Why it happens:** `get_section_slugs()` only returns top-level slugs (it's the backward-compat alias).
**How to avoid:** Use `get_section_paths(tree)` for the existing path set. Use `add_section(tree, slug, body, parent_path=...)` for new sections. Use `update_section_body(tree, path, body)` with full slash-separated path for existing sections.
**Warning signs:** Nested sections appear as new top-level sections in XML after merge.

### Pitfall 5: Section Marker Must Include Correct Slug
**What goes wrong:** The marker injection `f"<!-- section: {section_name} -->"` uses `args.section` which is just the leaf slug. This is correct -- markers identify the section by slug, not full path.
**Why it happens:** Could accidentally use the full parent/slug path in the marker.
**How to avoid:** Markers always use the bare slug (same as today). The tree position is determined by `--parent`, not the marker.
**Warning signs:** Markers contain slashes.

### Pitfall 6: Backward Compatibility for Top-Level-Only State
**What goes wrong:** Top-level sections written without `--parent` must still work identically to today. The section dict must gain `subsections: {}` and `subsections_order: []` even when no children are added.
**Why it happens:** Finalize code might crash if `subsections` key is absent.
**How to avoid:** Always initialize `subsections` and `subsections_order` when creating a section entry, even for top-level sections with no children.
**Warning signs:** Finalize crashes on `KeyError: 'subsections'` for leaf sections.

## Code Examples

### write-section.py section_write() with --parent

```python
def section_write(args):
    """Accumulate a section into the state file."""
    state = load_json(args.state_file, default={"documents": {}})

    # ... existing content/refs loading code unchanged ...

    doc_name = args.document
    if doc_name not in state["documents"]:
        state["documents"][doc_name] = {
            "header": "",
            "sections_order": [],
            "sections": {},
        }
    doc = state["documents"][doc_name]

    if header is not None:
        doc["header"] = header

    # Derive symbols and file_paths from typed_refs
    typed_refs = refs["typed_refs"]
    derived_symbols, derived_file_paths = _derive_symbols_and_file_paths(typed_refs)

    # Build the new section entry
    new_section = {
        "content": content,
        "symbols": derived_symbols,
        "file_paths": derived_file_paths,
        "typed_refs": typed_refs,
        "subsections": {},
        "subsections_order": [],
    }

    section_name = args.section
    parent_path = getattr(args, "parent", None)

    if parent_path:
        # Resolve parent in the state tree
        parent_section = _resolve_parent(doc, parent_path)

        # Ensure parent has subsections structure
        if "subsections" not in parent_section:
            parent_section["subsections"] = {}
        if "subsections_order" not in parent_section:
            parent_section["subsections_order"] = []

        # Insert or overwrite
        if section_name not in parent_section["subsections"]:
            parent_section["subsections_order"].append(section_name)
        parent_section["subsections"][section_name] = new_section
    else:
        # Top-level section (existing behavior + new keys)
        if section_name not in doc["sections"]:
            doc["sections_order"].append(section_name)
        doc["sections"][section_name] = new_section

    # Advisory symbol check, save state, print summary
    # ... unchanged ...
```

### finalize() state-to-XML conversion

```python
def _state_sections_to_xml(doc_data):
    """Convert state document data to list of section dicts for build_xml_doc."""
    sections = []
    for slug in doc_data.get("sections_order", []):
        section = doc_data.get("sections", {}).get(slug)
        if section:
            sections.append(_state_section_to_xml_section(slug, section))
    return sections

def _state_section_to_xml_section(slug, section_data):
    """Recursively convert state section to XML section format."""
    children = []
    for child_slug in section_data.get("subsections_order", []):
        child_data = section_data.get("subsections", {}).get(child_slug)
        if child_data:
            children.append(_state_section_to_xml_section(child_slug, child_data))
    return {
        "slug": slug,
        "body": section_data["content"],
        "children": children,
    }
```

### Recursive manifest building

```python
def _collect_manifest_entries(sections, sections_order, prefix=""):
    """Recursively collect manifest entries from nested state tree.

    Yields (path, symbols, file_paths) for sections with non-empty refs.
    """
    for slug in sections_order:
        section = sections.get(slug)
        if not section:
            continue
        path = f"{prefix}/{slug}" if prefix else slug
        symbols = section.get("symbols", [])
        file_paths = section.get("file_paths", [])
        if symbols or file_paths:
            yield path, symbols, file_paths
        # Recurse into subsections
        yield from _collect_manifest_entries(
            section.get("subsections", {}),
            section.get("subsections_order", []),
            path,
        )
```

### Recursive _written_sections collection

```python
def _collect_all_paths(sections, sections_order, prefix=""):
    """Collect all section paths from nested state tree."""
    paths = []
    for slug in sections_order:
        section = sections.get(slug)
        if not section:
            continue
        path = f"{prefix}/{slug}" if prefix else slug
        paths.append(path)
        paths.extend(_collect_all_paths(
            section.get("subsections", {}),
            section.get("subsections_order", []),
            path,
        ))
    return paths
```

### Updated parse_existing_sections for merge mode

```python
def parse_existing_sections(content):
    """Parse markdown into header + nested section list.

    Splits on ## through ##### headings. Returns flat list with depth info
    for merge matching by path.

    Returns:
        (header_text, [(path, heading_line, section_body), ...])
        where path is slash-separated (e.g., "monitoring/etl-logging").
    """
    # Split on heading markers at all levels
    parts = re.split(r"(?=^#{2,5} )", content, flags=re.MULTILINE)
    header = ""
    sections = []

    # Stack tracks current path at each depth level
    # depth 0 = ##, depth 1 = ###, etc.
    path_stack = []

    for i, part in enumerate(parts):
        if i == 0 and not re.match(r"^#{2,5} ", part):
            header = part
            continue

        lines = part.split("\n", 1)
        heading_line = lines[0]
        body = lines[1] if len(lines) > 1 else ""

        # Count heading level
        match = re.match(r"^(#{2,5}) ", heading_line)
        if not match:
            continue
        level = len(match.group(1))  # 2 for ##, 3 for ###, etc.
        depth = level - 2  # 0 for ##, 1 for ###, etc.

        heading_text = heading_line[level + 1:].strip()
        slug = slugify_heading(heading_text)

        # Trim stack to current depth
        path_stack = path_stack[:depth]
        path_stack.append(slug)
        path = "/".join(path_stack)

        sections.append((path, heading_line, body))

    return header, sections
```

### Updated assemble() in assemble-markdown.py

```python
from lib.xml_doc import parse_xml_doc, walk_sections

def assemble(xml_path):
    """Assemble markdown content from an XML document.

    Uses walk_sections for depth-first traversal, producing flat markdown
    output where nesting is implicit via heading levels.
    """
    doc = parse_xml_doc(xml_path)

    parts = []
    header = doc["meta"]["header"]
    if header:
        parts.append(header.rstrip("\n"))

    for path, section in walk_sections(doc["sections"]):
        body = section["body"]
        if body:
            parts.append(body.strip("\n"))

    return "\n\n".join(parts) + "\n"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat state: `sections` dict with slug keys | Nested state: sections gain `subsections`/`subsections_order` | Phase 19 | Writers can emit child sections; finalize produces nested XML |
| `parse_existing_sections` splits on `## ` only | Splits on `#{2,5} `, builds tree structure | Phase 19 | Merge mode handles nested documents correctly |
| `assemble()` iterates flat section list | Uses `walk_sections` for depth-first traversal | Phase 19 | Handles arbitrarily nested XML from Phase 18 |
| `get_section_slugs` for XML merge lookup | `get_section_paths` for path-based lookup | Phase 18 | Merge mode finds nested sections by path |

**Deprecated/outdated:**
- Flat state format (no `subsections`/`subsections_order`): clean cutover, no migration
- `parse_existing_sections` returning `(slug, heading_line, body)` tuples: now returns `(path, heading_line, body)` tuples

## Open Questions

1. **Merge mode: XML update for nested sections**
   - What we know: Current XML merge uses `get_section_slugs(tree)` (top-level only) and `add_section(tree, slug, body)` (root-level). Phase 18 added `get_section_paths(tree)` and `add_section(tree, slug, body, parent_path=...)`.
   - What's unclear: How to derive the parent_path for a new nested section during XML merge. The state tree knows the path, so the parent_path can be extracted from the section's path.
   - Recommendation: During XML merge, iterate all state sections recursively. For each, compute the full path. If path exists in `get_section_paths(tree)`, update body. If not, extract parent_path (all segments except last) and leaf slug, call `add_section(tree, slug, body, parent_path=parent_path)`.

2. **Finalize XML refs population for nested sections**
   - What we know: Current finalize builds XML then populates refs with `update_section_refs(tree, section_slug, typed_refs)`. With nesting, refs need to be populated at the correct path.
   - What's unclear: Whether to populate refs during build (inline) or after build (loop).
   - Recommendation: After `build_xml_doc`, walk the state tree recursively and call `update_section_refs(tree, path, typed_refs)` for each section that has typed_refs. This matches the existing pattern and uses the path-based addressing from Phase 18.

3. **Overwrite behavior for subsections**
   - What we know: Top-level sections can be overwritten (same slug, content replaced, order preserved). Same should apply to subsections.
   - What's unclear: Edge case when overwriting a subsection that has its own children -- should children be preserved?
   - Recommendation: Overwrite replaces content, symbols, file_paths, typed_refs but preserves existing subsections and subsections_order. This matches depth-first writer behavior where parent is written first, then children.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest auto-doc/scripts/tests/test_write_section.py auto-doc/scripts/tests/test_assemble_markdown.py --tb=short -q --no-header` |
| Full suite command | `uv run pytest --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WSA-01 | --parent flag places section at correct tree depth | unit | `uv run pytest auto-doc/scripts/tests/test_write_section.py -k "parent" --tb=short -q --no-header` | Needs new tests |
| WSA-02 | Parent must exist before child emitted | unit | `uv run pytest auto-doc/scripts/tests/test_write_section.py -k "parent_not_found" --tb=short -q --no-header` | Needs new tests |
| WSA-03 | Finalize produces nested XML | unit | `uv run pytest auto-doc/scripts/tests/test_write_section.py -k "finalize" --tb=short -q --no-header` | Existing tests need extension |
| WSA-04 | Merge mode handles nested headings | unit | `uv run pytest auto-doc/scripts/tests/test_write_section.py -k "merge" --tb=short -q --no-header` | Existing tests need extension |
| WSA-05 | assemble-markdown.py recursive depth-first | unit | `uv run pytest auto-doc/scripts/tests/test_assemble_markdown.py --tb=short -q --no-header` | Existing tests need extension |
| WSA-06 | Assembled output is flat markdown | unit | `uv run pytest auto-doc/scripts/tests/test_assemble_markdown.py -k "nested" --tb=short -q --no-header` | Needs new tests |
| WSA-07 | No dual-format state handling | unit | `uv run pytest auto-doc/scripts/tests/test_write_section.py --tb=short -q --no-header` | Verified by absence of migration code |

### Sampling Rate
- **Per task commit:** `uv run pytest auto-doc/scripts/tests/test_write_section.py auto-doc/scripts/tests/test_assemble_markdown.py --tb=short -q --no-header`
- **Per wave merge:** `uv run pytest --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. Tests in `test_write_section.py` and `test_assemble_markdown.py` already exist and will be extended with new test cases for nesting.

## Sources

### Primary (HIGH confidence)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/write-section.py` - Current implementation reviewed line-by-line (507 lines)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/assemble-markdown.py` - Current implementation reviewed (79 lines)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/lib/xml_doc.py` - Phase 18 recursive model reviewed (667 lines)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/tests/test_write_section.py` - 40 existing tests verified passing
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/tests/test_assemble_markdown.py` - 4 existing tests verified passing
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/tests/test_xml_doc.py` - 61 existing tests verified passing (including nested 2-3 level round-trips)
- `/home/mcbrain/mg_projects/mg-cc-tools/docs/work-queue/todo/recursive-section-xml/phase-docs/phase-19-nested-write-section-assembly.md` - Concept document with CLI examples, state format, and scope

### Secondary (MEDIUM confidence)
- Phase 18 RESEARCH.md and CONTEXT.md - Confirms xml_doc.py API surface and design decisions

### Tertiary (LOW confidence)
None -- all findings verified against source code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in use, no new dependencies
- Architecture: HIGH - patterns derived directly from existing code + Phase 18 API surface verified against source
- Pitfalls: HIGH - identified by line-by-line code review of affected functions

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (stable internal codebase, no external dependency drift)
