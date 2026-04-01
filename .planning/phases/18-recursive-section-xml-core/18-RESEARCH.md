# Phase 18: Recursive Section XML Core - Research

**Researched:** 2026-04-01
**Domain:** lxml recursive XML document model, tree-path navigation, Python recursive data structures
**Confidence:** HIGH

## Summary

Phase 18 transforms `lib/xml_doc.py` from a flat section model (all `<section>` elements are direct children of `<document>`) to a recursive nested model where `<section>` elements nest inside other `<section>` elements to mirror the markdown heading hierarchy. The core deliverable is seven functions in `xml_doc.py`: recursive `build_xml_doc`, recursive `parse_xml_doc`, `_find_section_by_path`, `walk_sections`, `get_section_paths` (renamed from `get_section_slugs`), and updated `update_section_body`/`update_section_refs`/`add_section` that accept slash-separated paths. Additionally, `schema.md` must document the nested XML model with examples.

The implementation is purely internal to `xml_doc.py` and its tests plus `schema.md`. No downstream scripts (write-section.py, verify-xml-refs.py, extract-edit-xml.py, etc.) are modified in this phase -- they are updated in Phases 19 and 20. The existing public API signatures change (slug parameters become path parameters), but bare slugs remain valid paths, providing backward compatibility for top-level sections that downstream scripts currently use.

**Primary recommendation:** Implement the seven functions iteratively, building from the leaf helper (`_find_section_by_path`) upward. All existing tests must be rewritten for the nested model since `build_xml_doc` gains a `children` key in its section dicts. Use parameterized tests at 1, 2, and 3 levels of nesting for round-trip fidelity.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- One element type (`<section>`), recursively nested -- no `<subsection>` or depth-specific types (D1)
- Every heading level (`##`, `###`, `####`, `#####`) produces its own `<section>` -- no depth cutoff (D3)
- A section's `<body>` holds only text between its heading and the first child heading -- never child content (D2)
- A section's `<refs>` correspond to its `<body>` only -- refs match body, always (D6)
- Sections with no child headings work exactly as today (leaf sections)
- `<!-- section: slug -->` markers at every heading level, same pattern, no depth-specific variants
- `parse_xml_doc` returns nested section dicts with keys: `slug`, `body`, `refs`, `children` (list, may be empty for leaf)
- Top-level `sections` is still a list of `##`-level sections
- `walk_sections(sections, prefix="")` yields `(path, section_dict)` tuples in depth-first order
- All functions that currently accept a bare `slug` parameter change to accept a slash-separated path
- A bare slug is a valid path (depth 1) -- backward-compatible for top-level sections
- `get_section_slugs(tree)` renamed to `get_section_paths(tree)` -- returns slash-separated paths for all sections at all depths
- `_find_section_by_path` walks the XML tree level by level, matching each slug segment against child `<section>` elements
- Slugs must be unique among siblings, not globally (D5)
- Clean cutover -- no code that reads both old and new formats (D4)
- Old flat-section XML files are regenerated from scratch, not migrated
- schema.md updated with nested `<section>` examples at 2-3 levels of nesting

### Claude's Discretion
- Internal implementation of `build_xml_doc` recursive builder (algorithm for constructing nested elements)
- How `add_section` handles the tree insertion (whether it validates parent existence, error behavior)
- Test organization and parameterization strategy for round-trip tests
- Whether `_find_section_by_path` raises or returns None on miss (concept shows returning None)

### Deferred Ideas (OUT OF SCOPE)
- write-section.py `--parent` flag and nested state format -- Phase 19
- assemble-markdown.py recursive concatenation -- Phase 19
- Downstream pipeline script updates (verify, extract, merge, sync, prepare, load-audit) -- Phase 20
- Writer agent prompt changes for per-heading emission -- Phase 21
- Stale writer modernization (end-user-writer, developer-writer, agent-writer) -- separate effort
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| XML-01 | Building XML from multiple heading levels produces recursive nested `<section>` elements -- one type at every depth with no cutoff | `build_xml_doc` recursive builder with `children` key in section dicts; lxml `SubElement` nesting confirmed to work at arbitrary depth |
| XML-02 | Each section's body contains only prose between its heading and next child heading -- never child content | Body isolation enforced by `build_xml_doc` accepting pre-split bodies; each section dict's `body` is independent of its `children` |
| XML-03 | Each section's refs declare exactly entities in its own body -- entity in child's body declared in child's refs only | Refs stored per-section independently; `update_section_refs` addressed by path to target correct section |
| XML-04 | Parsing returns nested structure traversable depth-first, yielding each section with slash-separated path | `parse_xml_doc` recursion + `walk_sections` helper yield `(path, section_dict)` tuples |
| XML-05 | All section-addressing operations accept slash-separated path at any depth, bare slugs remain valid | `_find_section_by_path` as shared implementation; bare slug is single-segment path |
| XML-06 | Slugs unique among siblings -- different parents may share a slug | Path resolution walks tree level-by-level, sibling uniqueness guarantees unambiguous resolution |
| XML-07 | Old flat-section XML files regenerated from scratch, no dual-format code | Clean cutover; `build_xml_doc` only produces nested format; `parse_xml_doc` only reads nested format |
| XML-08 | Schema reference document describes nested model with 2+ nesting levels | schema.md XML Schema section updated with recursive `<section>` examples |
| XML-09 | Round-trip fidelity: parse(serialize(build())) yields equivalent structure at all depths | Parameterized round-trip tests at 1, 2, 3 levels; refs and children preserved through cycle |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lxml | (existing) | XML tree manipulation with CDATA support | Already used by xml_doc.py; stdlib ElementTree cannot do CDATA |
| Python xml.etree concepts | 3.11+ | Tree traversal patterns | lxml's API mirrors ElementTree; `findall`, `SubElement`, `get` all standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | (existing) | Test framework | All test files for xml_doc.py |
| tempfile | stdlib | Temporary XML files for round-trip tests | Same pattern as existing test_xml_doc.py |

No new dependencies needed. This phase works entirely within the existing lxml-based stack.

## Architecture Patterns

### Recommended Project Structure
```
auto-doc/scripts/lib/
    xml_doc.py          # Modified: recursive build/parse/find/walk/paths + path-based mutations
auto-doc/references/
    schema.md           # Modified: nested XML examples in XML Schema section
auto-doc/scripts/tests/
    test_xml_doc.py     # Rewritten: tests for nested model with parameterized depth
```

### Pattern 1: Recursive Section Dict
**What:** Section dicts gain a `children` key (list of section dicts, may be empty). This is the in-memory representation used by `parse_xml_doc` and consumed by `walk_sections`.
**When to use:** Every function that works with parsed section data.
**Example:**
```python
# Source: concept.md parse_xml_doc return format
{
    "slug": "monitoring-alerting",
    "body": "<!-- section: monitoring-alerting -->\n## Monitoring & Alerting\n\nIntro text...",
    "refs": [...],
    "children": [
        {
            "slug": "etl-run-logging",
            "body": "<!-- section: etl-run-logging -->\n### ETL Run Logging\n\n...",
            "refs": [...],
            "children": []
        }
    ]
}
```

### Pattern 2: Recursive XML Build
**What:** `build_xml_doc` recursively creates nested `<section>` elements from section dicts with `children`.
**When to use:** Building new XML documents from structured data.
**Example:**
```python
# Recursive helper for building section elements
def _build_section(parent_el, section):
    """Build a <section> XML element with refs, body, and children."""
    section_el = etree.SubElement(parent_el, "section", slug=section["slug"])
    etree.SubElement(section_el, "refs")
    body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(section["body"])
    for child in section.get("children", []):
        _build_section(section_el, child)
```

### Pattern 3: Path-Based Tree Navigation
**What:** `_find_section_by_path` resolves a slash-separated path to an XML element by walking the tree level by level.
**When to use:** All mutation operations (update body, update refs, find section).
**Example:**
```python
# Source: concept.md _find_section_by_path reference implementation
def _find_section_by_path(root, path):
    """Resolve a slash-separated section path to an XML element."""
    node = root
    for slug in path.split("/"):
        match = None
        for child in node.findall("section"):
            if child.get("slug") == slug:
                match = child
                break
        if match is None:
            return None
        node = match
    return node
```

### Pattern 4: Recursive Parse
**What:** `parse_xml_doc` recursively parses nested `<section>` elements into section dicts with `children`.
**When to use:** Reading XML documents back into Python dicts.
**Example:**
```python
def _parse_section(section_el):
    """Parse a <section> element into a dict with children."""
    slug = section_el.get("slug")
    body = _text(section_el.find("body"))
    refs = _parse_refs(section_el.find("refs"))
    children = [_parse_section(child) for child in section_el.findall("section")]
    return {"slug": slug, "body": body, "refs": refs, "children": children}
```

### Pattern 5: Depth-First Walk
**What:** `walk_sections` yields `(path, section_dict)` tuples for flat iteration over the entire tree.
**When to use:** When downstream code needs to iterate all sections regardless of depth (replaces flat `for section in doc["sections"]` loops in Phases 19-20).
**Example:**
```python
# Source: concept.md walk_sections
def walk_sections(sections, prefix=""):
    """Yield (path, section) for all sections in depth-first order."""
    for section in sections:
        path = f"{prefix}/{section['slug']}" if prefix else section["slug"]
        yield path, section
        yield from walk_sections(section.get("children", []), path)
```

### Pattern 6: Recursive Path Collection
**What:** `get_section_paths` recursively collects all slash-separated paths from the XML tree.
**When to use:** Listing all sections in the document.
**Example:**
```python
def get_section_paths(tree):
    """Return ordered list of slash-separated section paths at all depths."""
    root = tree.getroot()
    paths = []
    _collect_paths(root, "", paths)
    return paths

def _collect_paths(parent, prefix, paths):
    for el in parent.findall("section"):
        slug = el.get("slug")
        path = f"{prefix}/{slug}" if prefix else slug
        paths.append(path)
        _collect_paths(el, path, paths)
```

### Anti-Patterns to Avoid
- **Flat `findall("section")` on root:** This was the old pattern. In the nested model, `root.findall("section")` only returns top-level sections. Use `_find_section_by_path` or recursive traversal instead.
- **Global slug assumption:** Slugs are only unique among siblings. Never search the entire tree for a slug -- always resolve by path.
- **Body containing child content:** A parent section's body must contain ONLY the text between its heading and the first child heading. Never concatenate child bodies into parent body.
- **Modifying `_find_section` to still accept bare slugs and search globally:** This would silently break when two sections share a slug under different parents. The function must use path-based resolution.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| XML tree construction | Manual string concatenation | lxml.etree.SubElement recursion | lxml handles CDATA, encoding, pretty_print, XML declaration |
| Path resolution | Multiple ad-hoc `findall` chains | Single `_find_section_by_path` | Centralizes the path-walking algorithm; used by 4+ call sites |
| Tree flattening | Per-caller recursive iteration | `walk_sections` helper | Single implementation ensures consistent depth-first ordering |
| Path collection | Manual recursive string building | `get_section_paths` | Consistent with `walk_sections` ordering |

**Key insight:** The recursive model has exactly one path-resolution algorithm (`_find_section_by_path`) and one iteration algorithm (`walk_sections`). Everything else is built on top of these two primitives. Building custom traversals per-caller leads to inconsistency and bugs.

## Common Pitfalls

### Pitfall 1: lxml `findall` Only Returns Direct Children
**What goes wrong:** `element.findall("section")` only returns direct child `<section>` elements, NOT descendants. This is correct behavior for the path-resolution algorithm but a trap if you expect it to find nested sections.
**Why it happens:** lxml/ElementTree `findall` with a simple tag name matches only direct children.
**How to avoid:** Use `_find_section_by_path` for targeted lookup. Use recursive traversal (or `.iter("section")` for full tree) when you need all sections regardless of depth.
**Warning signs:** Missing sections in output, empty results when sections exist deeper in the tree.

### Pitfall 2: Existing Tests Assume Flat Sections
**What goes wrong:** All 21 existing tests in `test_xml_doc.py` use flat section lists and call `get_section_slugs`. They will break when the API changes.
**Why it happens:** Tests were written for the flat model.
**How to avoid:** Rewrite tests comprehensively. Flat (leaf-only) documents should still work -- they're just nested sections with `children: []`. Add 2-level and 3-level test cases.
**Warning signs:** Test failures on `get_section_slugs` (renamed), `_find_section` (now path-based), or `build_xml_doc` (sections now need `children` key).

### Pitfall 3: CDATA and Mixed Content in lxml
**What goes wrong:** lxml handles CDATA through `etree.CDATA()`. When a `<section>` contains both child elements (`<refs>`, `<body>`) AND nested `<section>` elements, lxml must not confuse element ordering.
**Why it happens:** lxml preserves element order reliably, but you must ensure `<refs>` and `<body>` come before child `<section>` elements for consistent serialization.
**How to avoid:** In `_build_section`, always add `<refs>` and `<body>` before recursing into children. The recursive SubElement calls naturally append children after.
**Warning signs:** XML output has sections interleaved with refs/body in unexpected order.

### Pitfall 4: `build_xml_doc` Section Input Format Change
**What goes wrong:** The `sections` parameter to `build_xml_doc` currently accepts `[{"slug": str, "body": str}]`. The new format adds `"children"`. Callers that don't include `children` would break.
**Why it happens:** Format migration.
**How to avoid:** Default `children` to `[]` if absent: `section.get("children", [])`. This ensures backward compatibility for callers that pass flat section lists.
**Warning signs:** KeyError on `children` when building XML.

### Pitfall 5: `update_section_refs` and `update_section_body` Must Navigate by Path
**What goes wrong:** These functions currently call `_find_section(tree, slug)` which does a flat lookup. After the change, they must call `_find_section_by_path` which takes a path. If internal callers still pass bare slugs, it works (single-segment path). But the underlying `_find_section` must be rewritten.
**Why it happens:** Function signature change ripples through.
**How to avoid:** Rename internal `_find_section(tree, slug)` to use path-based resolution. The parameter name should change from `slug` to `path` in the public API of `update_section_body` and `update_section_refs`.
**Warning signs:** Flat-slug lookups silently fail for nested sections.

### Pitfall 6: `add_section` Needs a Parent Parameter
**What goes wrong:** `add_section(tree, slug, body)` currently appends to root. For nested sections, it needs to know WHERE to append.
**Why it happens:** Flat model had no concept of parent.
**How to avoid:** Add an optional `parent_path` parameter (default None = root). When provided, resolve the parent via `_find_section_by_path` and append the new section there.
**Warning signs:** All new sections end up at root level despite nested intent.

### Pitfall 7: Round-Trip Symmetry for Children Order
**What goes wrong:** If `parse_xml_doc` returns children in a different order than `build_xml_doc` expects, the round-trip test fails.
**Why it happens:** lxml preserves element order, but if build and parse use different traversal approaches, order could diverge.
**How to avoid:** Both build and parse use natural element order (insertion order for build, document order for parse). Test round-trip explicitly at 3 levels.
**Warning signs:** Round-trip tests pass for 1 level but fail for 2+ levels.

## Code Examples

Verified patterns from the concept document and existing codebase:

### Building a Nested XML Document
```python
# Source: concept.md + existing build_xml_doc pattern
def build_xml_doc(audience, diataxis, header, sections, title=None):
    root = etree.Element("document", audience=audience, diataxis=diataxis)

    # <meta> -- unchanged from current implementation
    meta = etree.SubElement(root, "meta")
    title_el = etree.SubElement(meta, "title")
    title_el.text = title or _extract_title(header)
    generated_el = etree.SubElement(meta, "generated")
    generated_el.text = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header_el = etree.SubElement(meta, "header")
    header_el.text = etree.CDATA(header)

    # <section> elements -- now recursive
    for sec in sections:
        _build_section(root, sec)

    return etree.ElementTree(root)

def _build_section(parent_el, section):
    section_el = etree.SubElement(parent_el, "section", slug=section["slug"])
    etree.SubElement(section_el, "refs")
    body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(section["body"])
    for child in section.get("children", []):
        _build_section(section_el, child)
```

### Parsing Nested XML
```python
# Source: concept.md parse_xml_doc return format
def parse_xml_doc(path):
    tree = etree.parse(path)
    root = tree.getroot()

    meta_el = root.find("meta")
    meta = {
        "title": _text(meta_el.find("title")),
        "generated": _text(meta_el.find("generated")),
        "header": _text(meta_el.find("header")),
    }

    sections = [_parse_section(el) for el in root.findall("section")]

    return {
        "audience": root.get("audience"),
        "diataxis": root.get("diataxis"),
        "meta": meta,
        "sections": sections,
    }

def _parse_section(section_el):
    slug = section_el.get("slug")
    body = _text(section_el.find("body"))
    refs = _parse_refs(section_el.find("refs"))
    children = [_parse_section(child) for child in section_el.findall("section")]
    return {"slug": slug, "body": body, "refs": refs, "children": children}
```

### Path-Based Section Lookup
```python
# Source: concept.md reference implementation
def _find_section_by_path(root, path):
    node = root
    for slug in path.split("/"):
        match = None
        for child in node.findall("section"):
            if child.get("slug") == slug:
                match = child
                break
        if match is None:
            return None
        node = match
    return node
```

### Updated Mutation Helpers (Signature Change)
```python
# update_section_body and update_section_refs change slug -> path
def update_section_body(tree, path, new_body):
    section_el = _find_section(tree, path)  # _find_section now delegates to _find_section_by_path
    body_el = section_el.find("body")
    if body_el is None:
        body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(new_body)
    return tree

def _find_section(tree, path):
    """Find a <section> element by path, or raise ValueError."""
    root = tree.getroot()
    el = _find_section_by_path(root, path)
    if el is None:
        raise ValueError(f"Section not found: {path}")
    return el
```

### add_section with Optional Parent
```python
def add_section(tree, slug, body, parent_path=None):
    root = tree.getroot()
    if parent_path:
        parent_el = _find_section_by_path(root, parent_path)
        if parent_el is None:
            raise ValueError(f"Parent section not found: {parent_path}")
    else:
        parent_el = root
    section_el = etree.SubElement(parent_el, "section", slug=slug)
    etree.SubElement(section_el, "refs")
    body_el = etree.SubElement(section_el, "body")
    body_el.text = etree.CDATA(body)
    return tree
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat `<section>` children of `<document>` | Recursive nested `<section>` elements | Phase 18 | Per-heading ref tracking, smaller edit units |
| `get_section_slugs` returning flat slugs | `get_section_paths` returning slash-separated paths | Phase 18 | All sections addressable at any depth |
| `_find_section` by flat slug scan | `_find_section_by_path` by tree walk | Phase 18 | Supports nested sections, sibling-unique slugs |
| Section body includes child heading content | Section body is intro only, children separate | Phase 18 | Precise ref-to-body correspondence |

**Deprecated/outdated:**
- `get_section_slugs(tree)`: Renamed to `get_section_paths(tree)`. Name should not appear in new code.
- Flat `_find_section(tree, slug)` with `root.findall("section")` scan: Replaced by path-based resolution.

## Open Questions

1. **Should `_find_section_by_path` return None or raise on miss?**
   - What we know: The concept document shows it returning None. The current `_find_section` raises ValueError.
   - What's unclear: Both approaches have merits. Returning None is safer for optional lookups; raising is safer for mandatory lookups.
   - Recommendation: Have `_find_section_by_path` return None (pure navigation primitive). Keep `_find_section` as a raising wrapper that calls `_find_section_by_path` -- this matches the current error contract for `update_section_body` and `update_section_refs`. This is the pattern shown in the concept doc.

2. **Should `build_xml_doc` require `children` in input dicts?**
   - What we know: Current callers pass `[{"slug": ..., "body": ...}]` without `children`.
   - What's unclear: Whether we enforce the new format immediately or default missing `children` to `[]`.
   - Recommendation: Default to `[]` via `.get("children", [])`. This avoids breaking callers that build flat section lists (which still works -- they're just leaf sections). Downstream scripts (Phase 19-20) can add children later.

3. **Should `add_section` validate sibling slug uniqueness?**
   - What we know: D5 says slugs must be unique among siblings.
   - What's unclear: Whether to enforce at build time or treat as a data quality issue caught at verify time.
   - Recommendation: Validate at add_section time -- raise ValueError if a sibling with the same slug already exists. This is cheap (linear scan of parent's children) and catches bugs early.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py --tb=short -q --no-header` |
| Full suite command | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| XML-01 | Multi-level heading produces nested `<section>` elements | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestBuildAndParse -x` | Rewrite needed |
| XML-02 | Body contains only own prose, not child content | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestBuildAndParse::test_body_isolation -x` | New test |
| XML-03 | Refs per-section only (not inherited from children) | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestUpdateSectionRefs -x` | Rewrite needed |
| XML-04 | Parsing returns nested structure, walk_sections yields paths | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestWalkSections -x` | New test class |
| XML-05 | Slash-separated path addressing works for find/update/list | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestFindSectionByPath -x` | New test class |
| XML-06 | Sibling slug uniqueness (duplicate slugs under same parent rejected) | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestAddSection -x` | New test |
| XML-07 | No dual-format reading code | manual-only | Code review: no old-format parse path exists | N/A |
| XML-08 | Schema.md documents nested model with 2+ levels | manual-only | Review schema.md XML examples | N/A |
| XML-09 | Round-trip fidelity at 1, 2, 3 levels | unit | `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py::TestRoundTrip -x` | New parameterized test class |

### Sampling Rate
- **Per task commit:** `python3 -m pytest auto-doc/scripts/tests/test_xml_doc.py --tb=short -q --no-header`
- **Per wave merge:** `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `auto-doc/scripts/tests/test_xml_doc.py` -- rewrite all existing tests for nested model, add new test classes (TestWalkSections, TestFindSectionByPath, TestRoundTrip, TestGetSectionPaths)
- No framework install needed (pytest already present)
- No conftest changes needed (tests are self-contained with tempfile)

## Downstream Impact Analysis (Informational)

These scripts consume `xml_doc.py` functions and will need updates in Phase 19/20. Documenting their current usage patterns here so the planner understands the API contract boundaries.

| Script | Functions Used | Phase for Update |
|--------|---------------|-----------------|
| `write-section.py` | `build_xml_doc`, `parse_xml_doc`, `add_section`, `update_section_body`, `update_section_refs`, `get_section_slugs`, `serialize_xml_doc` | Phase 19 |
| `verify-xml-refs.py` | `parse_xml_doc` (iterates `doc["sections"]` flat) | Phase 20 |
| `extract-edit-xml.py` | Direct `root.findall("section")` flat scan | Phase 20 |
| `merge-edit-xml.py` | `update_section_body`, `update_section_refs`, `serialize_xml_doc`, direct `findall("section")` | Phase 20 |
| `assemble-markdown.py` | `parse_xml_doc` (iterates `doc["sections"]` flat) | Phase 19 |
| `sync-edits-to-xml.py` | `parse_xml_doc`, `update_section_body`, `serialize_xml_doc` | Phase 20 |
| `prepare-prose-verify.py` | `parse_xml_doc` (iterates `doc["sections"]` flat) | Phase 20 |

**Key insight for planner:** After Phase 18, the `xml_doc.py` API changes but downstream scripts still work IF they only use top-level sections (bare slugs as single-segment paths). The `parse_xml_doc` return format gains `children` keys but existing code that does `for section in doc["sections"]` still gets top-level sections -- it just misses nested ones. The full suite of downstream tests may break on the `get_section_slugs` rename, so the planner should sequence carefully.

## Sources

### Primary (HIGH confidence)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/lib/xml_doc.py` -- current implementation, 494 lines
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/tests/test_xml_doc.py` -- current test suite, 21 tests
- `/home/mcbrain/mg_projects/mg-cc-tools/docs/work-queue/todo/recursive-section-xml/concept.md` -- authoritative design document
- `/home/mcbrain/mg_projects/mg-cc-tools/docs/work-queue/todo/recursive-section-xml/phase-docs/phase-18-recursive-section-xml-core.md` -- phase-specific scope and verification
- `/home/mcbrain/mg_projects/mg-cc-tools/.planning/phases/18-recursive-section-xml-core/18-CONTEXT.md` -- locked decisions

### Secondary (MEDIUM confidence)
- `/home/mcbrain/mg_projects/mg-cc-tools/.serena/memories/auto-doc/subsection-xml-research.md` -- earlier research (predates final concept; some suggestions superseded by D1 uniform `<section>` decision)
- lxml documentation on SubElement, CDATA, findall behavior -- verified against existing working code patterns

### Tertiary (LOW confidence)
- None. All findings verified against source code and concept documents.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, existing lxml patterns verified by 21 passing tests
- Architecture: HIGH -- concept doc provides exact function signatures, return formats, and reference implementations
- Pitfalls: HIGH -- identified from actual code analysis of current flat model and lxml behavior
- Validation: HIGH -- existing test infrastructure, clear requirement-to-test mapping

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (stable internal codebase, no external dependency changes)
