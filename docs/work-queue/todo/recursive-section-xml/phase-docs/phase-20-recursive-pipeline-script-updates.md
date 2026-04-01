# Phase 20: Recursive Pipeline Script Updates

> Source: docs/work-queue/todo/recursive-section-xml/concept.md
> Phase goal: verify-xml-refs.py, prepare-prose-verify.py, extract-edit-xml.py, merge-edit-xml.py, sync-edits-to-xml.py, and load-audit-findings.py operate on the recursive section tree using slash-separated section paths
> Requirements: TBD

---

## Finding Path Format

Findings identify their section using a slash-separated path in the `"section"` field:

```json
{
  "document": "OPERATIONS",
  "section": "monitoring-alerting/etl-run-logging",
  "audience": "devops",
  "check": "reference-integrity",
  "description": "Function `start_run` not mentioned in prose"
}
```

Leaf slug: `path.rsplit("/", 1)[-1]`. Parent path: `path.rsplit("/", 1)[0]`. One field, any depth.

## Tree-Path Navigation

*(Built in Phase 18 — `_find_section_by_path` lives in xml_doc.py)*

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
- `extract-edit-xml.py` to locate the section to extract
- `merge-edit-xml.py` to locate the section to update
- `verify-xml-refs.py` when resolving finding paths back to sections
- `_find_section()` in `xml_doc.py` as the shared implementation

Slug uniqueness within parent (D5) guarantees that each path resolves to exactly one node.

## Marker-Based Body Splitting

`sync-edits-to-xml.py` splits markdown into sections using `<!-- section: slug -->` markers. With nested sections, consecutive markers naturally delimit each body:

```markdown
<!-- section: monitoring-alerting -->
## Monitoring & Alerting

Intro text...
<!-- section: etl-run-logging -->
### ETL Run Logging

Every flow creates a row...
<!-- section: health-artifact -->
### Health Artifact

Each flow publishes...
```

A flat split by marker gives three segments. The nesting is reconstructed by reading the heading level (`##`, `###`, etc.) in each segment. A `###` segment following a `##` segment is its child; a `###` segment following another `###` is a sibling. The heading level in the body content is the authoritative signal for tree position — markers provide identity (the slug), headings provide hierarchy (the depth).

## Edit-Group XML Format

The `<edit-group>` XML produced by `extract-edit-xml.py` adds a `path` attribute to each `<section>` element, carrying the full slash-separated path for merge-back:

```xml
<edit-group id="etl-tracking-funcs">
  <summary>ETL tracking functions not named in prose</summary>
  <section source="/abs/path/OPERATIONS.xml"
           path="monitoring-alerting/etl-run-logging"
           slug="etl-run-logging"
           audience="devops" document="OPS">
    <findings>...</findings>
    <refs>...</refs>
    <body><![CDATA[...]]></body>
  </section>
</edit-group>
```

`merge-edit-xml.py` uses the `path` attribute with `_find_section_by_path()` to locate the correct node in the master XML tree. The `slug` attribute is retained for display/logging.

## Downstream Pipeline Changes

- **verify-xml-refs.py**: Recursive iteration over nested sections. Each section's refs checked against its own body independently.
- **extract-edit-xml.py**: Uses `_find_section_by_path()` to extract individual sections at any depth. Edit files shrink from 200 lines to 5-40 lines.
- **merge-edit-xml.py**: Uses `_find_section_by_path()` to merge back to the correct tree position.
- **sync-edits-to-xml.py**: Splits on markers, reconstructs tree from heading levels.
- **prepare-prose-verify.py**: Recursively iterates nested sections. Output files use nested directories mirroring the section tree (e.g., `{output_dir}/monitoring-alerting/etl-run-logging.json`). This mirrors the XML structure and avoids flat-name collisions.
- **load-audit-findings.py**: Handles slash-separated section paths in findings.
- **fix-queue.py**: No structural changes — operates on whatever sections extract produces.
- **audit-fixer.md**: Receives smaller edit files naturally. Scope creep constrained by body size.

## Design Decisions

### D7: Slash-separated section path in findings

**Choice:** Findings use a single `"section"` field with slash-separated paths: `"monitoring-alerting/etl-run-logging"`.

**Why:** The path is the identifier. Splitting across fields (`section`, `subsection`) reintroduces depth-specific naming, and every consumer would reassemble the path anyway. One field works at any depth. Leaf and parent are trivially derived via `rsplit("/", 1)`.

**Alternatives rejected:** Separate fields per depth level — doesn't work with recursive nesting (would need `subsubsection`, etc.).

## Scope

| Area | Changes |
|------|---------|
| `verify-xml-refs.py` | Recursive section iteration. Finding `"section"` field uses slash-separated paths |
| `extract-edit-xml.py` | Extracts sections at any tree depth. Edit files are small |
| `merge-edit-xml.py` | Merges back to correct tree position using section path |
| `sync-edits-to-xml.py` | Splits markdown on markers, reconstructs tree from heading levels |
| `prepare-prose-verify.py` | Recursively iterates nested sections for prose verification input |
| `load-audit-findings.py` | Handles slash-separated section paths in findings |

## Verification

5. **Edit extraction size**: Compare edit XML token count for old (flat) vs new (nested) model on the same group of findings. Expect >50% reduction for multi-subsection groups.

7. **Slash-path resolution**: Verify that `extract-edit-xml.py` and `merge-edit-xml.py` correctly resolve slash-separated section paths to the right tree nodes.

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
*Phase: 20-recursive-pipeline-script-updates*
*Date: 2026-04-01*
