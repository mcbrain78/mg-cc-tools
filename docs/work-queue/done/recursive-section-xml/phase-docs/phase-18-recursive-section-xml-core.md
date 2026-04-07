# Phase 18: Recursive Section XML Core

> Source: docs/work-queue/todo/recursive-section-xml/concept.md
> Phase goal: xml_doc.py supports recursive section nesting with `_find_section_by_path`, `walk_sections`, `get_section_paths`, and path-based navigation functions, and schema.md documents the nested XML model
> Requirements: TBD

---

## XML Structure

```xml
<section slug="monitoring-alerting">
  <refs><!-- refs for intro text only --></refs>
  <body><![CDATA[<!-- section: monitoring-alerting -->
## Monitoring & Alerting

Intro text...]]></body>
  <section slug="etl-run-logging">
    <refs><!-- start_run, complete_run, fail_run --></refs>
    <body><![CDATA[<!-- section: etl-run-logging -->
### ETL Run Logging

Every flow creates a row...]]></body>
  </section>
  <section slug="health-artifact">
    <refs><!-- create_health_summary_artifact --></refs>
    <body><![CDATA[<!-- section: health-artifact -->
### Health Artifact

Each flow publishes...]]></body>
    <section slug="artifact-format">
      <refs><!-- _build_health_summary_markdown --></refs>
      <body><![CDATA[<!-- section: artifact-format -->
#### Artifact Format

The markdown artifact contains...]]></body>
    </section>
  </section>
</section>
```

Key properties:
- One element type (`<section>`), recursively nested
- A section's `<body>` holds only the text between its heading and the first child heading — never child content
- A section's `<refs>` correspond to its `<body>` only — refs match body, always
- Sections with no child headings work exactly as today (leaf sections)
- `<!-- section: slug -->` markers at every heading level (same pattern, no depth-specific variants)

## `parse_xml_doc` Return Format

`parse_xml_doc` returns nested section dicts mirroring the XML tree. Each section has a `children` list (may be empty for leaf sections):

```json
{
  "audience": "devops",
  "diataxis": "how-to",
  "meta": {"header": "...", "title": "...", "generated": "..."},
  "sections": [
    {
      "slug": "monitoring-alerting",
      "body": "<!-- section: monitoring-alerting -->\n## Monitoring & Alerting\n\nIntro text...",
      "refs": [...],
      "children": [
        {
          "slug": "etl-run-logging",
          "body": "<!-- section: etl-run-logging -->\n### ETL Run Logging\n\n...",
          "refs": [{"type": "code", "kind": "function", "name": "start_run"}],
          "children": []
        },
        {
          "slug": "health-artifact",
          "body": "...",
          "refs": [...],
          "children": [
            {"slug": "artifact-format", "body": "...", "refs": [...], "children": []}
          ]
        }
      ]
    }
  ]
}
```

Top-level `sections` is still a list of `##`-level sections. Each section's `children` contains its nested `###`-level sections, and so on recursively. Scripts that need flat iteration use `walk_sections(sections)`, a recursive helper in `xml_doc.py` that yields `(path, section_dict)` tuples in depth-first order:

```python
def walk_sections(sections, prefix=""):
    """Yield (path, section) for all sections in depth-first order."""
    for section in sections:
        path = f"{prefix}/{section['slug']}" if prefix else section["slug"]
        yield path, section
        yield from walk_sections(section.get("children", []), path)
```

Scripts that need path-based lookup on the XML tree use `_find_section_by_path`.

All functions that currently accept a bare `slug` parameter (`update_section_body`, `update_section_refs`, `_find_section`) change to accept a slash-separated path. A bare slug is a valid path (depth 1). This is backward-compatible for top-level sections and extends naturally for nested ones. `get_section_slugs(tree)` changes to `get_section_paths(tree)` and returns slash-separated paths for all sections at all depths.

## Tree-Path Navigation

All scripts that locate a section in the XML tree share a common algorithm: `_find_section_by_path(root, "monitoring-alerting/etl-run-logging")` walks the tree level by level, matching each slug segment against child `<section>` elements. This replaces the current flat `findall("section")` lookup.

```python
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

This function is used by:
- `extract-edit-xml.py` to locate the section to extract *(consumed by Phase 20)*
- `merge-edit-xml.py` to locate the section to update *(consumed by Phase 20)*
- `verify-xml-refs.py` when resolving finding paths back to sections *(consumed by Phase 20)*
- `_find_section()` in `xml_doc.py` as the shared implementation

Slug uniqueness within parent (D5) guarantees that each path resolves to exactly one node.

## Design Decisions

### D1: Uniform recursive `<section>` nesting

**Choice:** One `<section>` element type at all levels, nested to mirror the markdown heading hierarchy.

**Why:** One element type means one set of parse/build/update/verify functions. The heading hierarchy is already a tree; the XML should be the same tree. A separate `<subsection>` type would create an artificial boundary that the markdown doesn't have and would require depth-specific code paths.

### D2: Body contains only direct content, not children

**Choice:** A section's `<body>` holds only the text between its heading and the first child heading.

**Why:** This is what makes ref tracking precise. A section's `<refs>` correspond to its `<body>` — nothing more. The writer knows exactly which entities it just wrote about because the body is 5-40 lines, not 200.

### D3: Every heading level becomes a section

**Choice:** No depth cutoff. `##`, `###`, `####`, `#####` — any heading that exists in the markdown gets its own `<section>` with its own refs and body.

**Why:** The document author chose the heading structure. If they wrote a `####`, that's a meaningful boundary. Imposing an arbitrary cutoff would lose precision at exactly the points where the author decided to add structure. In practice `####` is rare and `#####` essentially nonexistent, so this costs nothing but eliminates a special case. The recursive implementation handles arbitrary depth with the same code paths used for two levels — supporting deeper nesting adds zero implementation complexity.

### D4: No backward compatibility layer

**Choice:** Clean cutover for the structural migration. Old flat-section XML files are regenerated, not migrated. No code that reads both old and new formats.

**Why:** Single-developer tool with controlled deployments. A compatibility layer would add complexity for zero users.

**Note:** This covers the migration from flat to nested XML. The `--merge` flag in `write-section.py` (used by the update pipeline for incremental section updates) is a separate concern — it is updated for the nested model, not removed. *(merge mode updated in Phase 19)*

### D5: Slug uniqueness is within parent

**Choice:** Slugs must be unique among siblings, not globally. Navigation uses tree path (slash-separated).

**Why:** Mirrors markdown — two sections can have a `### Prerequisites` heading as long as they're under different parents. Global uniqueness would force artificial disambiguation.

### D6: Refs match body, always

**Choice:** A section's `<refs>` declares exactly the entities mentioned in that section's `<body>` — no more, no less. If the same entity appears in both a parent's body and a child's body, both sections declare it. If it only appears in the child's body, only the child declares it.

**Why:** Each section is self-contained. Its refs describe what its body references. The audit checks each section's refs against its own body independently. A ref in a parent's `<refs>` that only appears in a child's body (not the parent's intro) correctly fails the parent's audit — the fix is to remove it from the parent's refs.

**Alternatives rejected:** "Refs only at deepest mention" — breaks self-containment. Extracting a parent section for editing would show incomplete refs for its body.

## Scope

| Area | Changes |
|------|---------|
| `lib/xml_doc.py` | Recursive section model — `build_xml_doc`, `parse_xml_doc`, `add_section`, `update_section_body`, `update_section_refs`, `_find_section` all become tree-aware. `get_section_slugs` renamed to `get_section_paths` (returns slash-separated paths). New `walk_sections` helper for flat iteration |
| `schema.md` | Updated XML examples and ref type documentation |
| All test files | Updated for nested structure |

## Verification

1. **Round-trip fidelity**: `build_xml_doc` → `serialize_xml_doc` → `parse_xml_doc` produces identical nested structure at any depth. Parameterized test with 1, 2, 3 levels of nesting.

2. **Heading-level coverage**: For a document with `##`, `###`, `####` headings, verify each heading produces its own `<section>` at the correct nesting depth in the XML tree.

3. **Body isolation**: For a parent section with children, verify the parent's `<body>` contains only intro text — no child heading content leaks into it.

4. **Ref precision**: For a section tree with known refs split across children, verify each ref lives only in the `<section>` whose `<body>` mentions it.

## Additional Context

### Situation

The auto-doc XML model has a flat section structure: each `##` heading becomes a `<section>` with one `<refs>` block and one `<body>` CDATA containing all `###`/`####` content as unstructured text. The writer already works section-by-section, emitting each section's body and `typed_refs` separately via `write-section.py`. The audit/fix/verify pipeline operates at section granularity.

Generated docs today have:
- 2-4 `##` sections per document
- 3-8 `###` subsections per section (present in the markdown, not tracked in XML)
- `####` headings are rare but exist

A typical OPERATIONS section like "Monitoring & Alerting" carries ~30 refs in a single `<refs>` block covering a ~200-line body, even though specific refs (like `start_run`) only matter for specific subsections (like "ETL Run Logging").

Refs are produced inline by writer agents during generation (as `typed_refs` in the section refs JSON), not extracted post-hoc. The writer has the best context for ref assignment — it knows exactly which entities it's writing about as it writes each heading's content.

### Problem

1. **Imprecise ref verification.** A reference-integrity check asks "does `start_run` appear in this section's prose?" across 200 lines. The ref might only be relevant to the 20-line "ETL Run Logging" subsection. This produces false positives and misses precision — a ref could appear in the wrong subsection and still pass.

2. **Oversized edit units.** The fix pipeline extracts entire sections into edit XML files. A group spanning 4 sections (alembic-env-py, 8 findings) produced a 10k+ token edit file. Fixer agents see 200 lines of body and add contextual entity names that create new audit findings — the scope-creep problem observed on road-runner where fixing 47 findings produced 17 new ones, many introduced by agents embellishing beyond their mandate.

3. **Ref assignment is all-or-nothing.** The writer emits one `typed_refs` blob for an entire section. It has to decide which refs "belong to" a 200-line body. The audit then discovers mismatches. With per-heading sections, each write would be 5-40 lines — the writer knows exactly which entities it just referenced because it just wrote about them.

### What does NOT get built

- **Migration tool** — old XML files are regenerated from scratch
- **Depth-specific marker variants** — no `<!-- section-3: slug -->`, same marker everywhere
- **Content restructuring** — the writer doesn't add or remove headings; it writes the same markdown

---

*Prepared from: docs/work-queue/todo/recursive-section-xml/concept.md*
*Phase: 18-recursive-section-xml-core*
*Date: 2026-04-01*
