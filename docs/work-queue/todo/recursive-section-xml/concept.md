# Recursive Section XML Model

## Situation

The auto-doc XML model has a flat section structure: each `##` heading becomes a `<section>` with one `<refs>` block and one `<body>` CDATA containing all `###`/`####` content as unstructured text. The writer already works section-by-section, emitting each section's body and `typed_refs` separately via `write-section.py`. The audit/fix/verify pipeline operates at section granularity.

Generated docs today have:
- 2-4 `##` sections per document
- 3-8 `###` subsections per section (present in the markdown, not tracked in XML)
- `####` headings are rare but exist

A typical OPERATIONS section like "Monitoring & Alerting" carries ~30 refs in a single `<refs>` block covering a ~200-line body, even though specific refs (like `start_run`) only matter for specific subsections (like "ETL Run Logging").

Refs are produced inline by writer agents during generation (as `typed_refs` in the section refs JSON), not extracted post-hoc. The writer has the best context for ref assignment — it knows exactly which entities it's writing about as it writes each heading's content.

## Problem

1. **Imprecise ref verification.** A reference-integrity check asks "does `start_run` appear in this section's prose?" across 200 lines. The ref might only be relevant to the 20-line "ETL Run Logging" subsection. This produces false positives and misses precision — a ref could appear in the wrong subsection and still pass.

2. **Oversized edit units.** The fix pipeline extracts entire sections into edit XML files. A group spanning 4 sections (alembic-env-py, 8 findings) produced a 10k+ token edit file. Fixer agents see 200 lines of body and add contextual entity names that create new audit findings — the scope-creep problem observed on road-runner where fixing 47 findings produced 17 new ones, many introduced by agents embellishing beyond their mandate.

3. **Ref assignment is all-or-nothing.** The writer emits one `typed_refs` blob for an entire section. It has to decide which refs "belong to" a 200-line body. The audit then discovers mismatches. With per-heading sections, each write would be 5-40 lines — the writer knows exactly which entities it just referenced because it just wrote about them.

## Solution

### Overview

Extend the XML document model so every markdown heading (`##`, `###`, `####`, etc.) produces its own `<section>` element, recursively nested to mirror the heading hierarchy. Each section carries its own `<refs>` and `<body>`. The writer emits sections individually via `write-section.py` (same pattern as today, finer grain). All downstream pipeline steps — verify, audit, fix, assemble — operate at per-heading granularity.

### XML Structure

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

### Writer Changes

The writer's prose output does not change — it still writes the same markdown with the same headings. The emission granularity changes: instead of one `write-section.py` call per `##` heading, the writer calls it once for the `##` intro and once for each `###`, `####`, etc. heading within that section.

Each call emits a small body (5-40 lines) with precisely scoped `typed_refs`. The writer knows exactly which entities it referenced because it just wrote about them — the ref-assignment problem shrinks from "which of 30 refs belong to this 200-line body" to "which refs did I just use in these 3 paragraphs."

Writer agent prompts (e.g., `devops-writer.md`) change from "for each `##` section, write content and call `write-section.py`" to "for each `##` section, write the intro and call `write-section.py`, then for each `###` heading write its content and call `write-section.py` with `--parent` set to the `##` slug, then for each `####` heading call with `--parent` set to the `##/###` path." The writer already processes sections sequentially from the template — this extends the existing loop to recurse into child headings.

### write-section.py CLI Interface

The existing `--section` flag identifies the section slug. A new `--parent` flag specifies where in the tree to insert it:

```bash
# Top-level section (## heading) — no --parent
python3 write-section.py --state-file STATE --document OPS \
    --section monitoring-alerting --content-file BODY --refs-file REFS

# Child section (### heading) — --parent is the parent slug
python3 write-section.py --state-file STATE --document OPS \
    --section etl-run-logging --parent monitoring-alerting \
    --content-file BODY --refs-file REFS

# Grandchild section (#### heading) — --parent is the slash-separated path
python3 write-section.py --state-file STATE --document OPS \
    --section artifact-format --parent monitoring-alerting/health-artifact \
    --content-file BODY --refs-file REFS
```

Rules:
- `--parent` omitted → top-level section (appended to `sections_order`)
- `--parent` is a slug → child of that top-level section
- `--parent` is a slash-separated path → child at the resolved tree position
- Parent must exist before child is emitted (writer processes depth-first: heading intro, then each child heading in order)
- `section_write()` traverses the state tree using the parent path, creates the `subsections` dict and `subsections_order` list at the resolved parent if they don't exist, then inserts the new section

### write-section.py State Format

```json
{
  "documents": {
    "OPS": {
      "sections": {
        "monitoring-alerting": {
          "content": "intro text...",
          "typed_refs": [...],
          "subsections": {
            "etl-run-logging": {
              "content": "...",
              "typed_refs": [...],
              "subsections": {},
              "subsections_order": []
            },
            "health-artifact": {
              "content": "...",
              "typed_refs": [...],
              "subsections": {
                "artifact-format": {
                  "content": "...",
                  "typed_refs": [...],
                  "subsections": {},
                  "subsections_order": []
                }
              },
              "subsections_order": ["artifact-format"]
            }
          },
          "subsections_order": ["etl-run-logging", "health-artifact"]
        }
      }
    }
  }
}
```

Finalize recursively builds nested `<section>` XML elements from this tree.

### `parse_xml_doc` Return Format

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

### Finding Path Format

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

### Tree-Path Navigation

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

### Marker-Based Body Splitting

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

### Edit-Group XML Format

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

### Downstream Pipeline Changes

- **assemble-markdown.py**: Recursive depth-first concatenation — section body, then child section bodies in order.
- **verify-xml-refs.py**: Recursive iteration over nested sections. Each section's refs checked against its own body independently.
- **extract-edit-xml.py**: Uses `_find_section_by_path()` to extract individual sections at any depth. Edit files shrink from 200 lines to 5-40 lines.
- **merge-edit-xml.py**: Uses `_find_section_by_path()` to merge back to the correct tree position.
- **sync-edits-to-xml.py**: Splits on markers, reconstructs tree from heading levels.
- **prepare-prose-verify.py**: Recursively iterates nested sections. Output files use nested directories mirroring the section tree (e.g., `{output_dir}/monitoring-alerting/etl-run-logging.json`). This mirrors the XML structure and avoids flat-name collisions.
- **fix-queue.py**: No structural changes — operates on whatever sections extract produces.
- **audit-fixer.md**: Receives smaller edit files naturally. Scope creep constrained by body size.

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

**Note:** This covers the migration from flat to nested XML. The `--merge` flag in `write-section.py` (used by the update pipeline for incremental section updates) is a separate concern — it is updated for the nested model, not removed.

### D5: Slug uniqueness is within parent

**Choice:** Slugs must be unique among siblings, not globally. Navigation uses tree path (slash-separated).

**Why:** Mirrors markdown — two sections can have a `### Prerequisites` heading as long as they're under different parents. Global uniqueness would force artificial disambiguation.

### D6: Refs match body, always

**Choice:** A section's `<refs>` declares exactly the entities mentioned in that section's `<body>` — no more, no less. If the same entity appears in both a parent's body and a child's body, both sections declare it. If it only appears in the child's body, only the child declares it.

**Why:** Each section is self-contained. Its refs describe what its body references. The audit checks each section's refs against its own body independently. A ref in a parent's `<refs>` that only appears in a child's body (not the parent's intro) correctly fails the parent's audit — the fix is to remove it from the parent's refs.

**Alternatives rejected:** "Refs only at deepest mention" — breaks self-containment. Extracting a parent section for editing would show incomplete refs for its body.

### D7: Slash-separated section path in findings

**Choice:** Findings use a single `"section"` field with slash-separated paths: `"monitoring-alerting/etl-run-logging"`.

**Why:** The path is the identifier. Splitting across fields (`section`, `subsection`) reintroduces depth-specific naming, and every consumer would reassemble the path anyway. One field works at any depth. Leaf and parent are trivially derived via `rsplit("/", 1)`.

**Alternatives rejected:** Separate fields per depth level — doesn't work with recursive nesting (would need `subsubsection`, etc.).

### D8: Writer markdown output unchanged

**Choice:** The writer produces the same markdown prose with the same headings it does today. Only the emission granularity changes — finer-grained `write-section.py` calls.

**Why:** This is a structural change to the XML model, not a content directive. Whether a section should have more or fewer headings is a template/content decision independent of how the XML tracks them.

## Scope

### What gets built

| Area | Changes |
|------|---------|
| `lib/xml_doc.py` | Recursive section model — `build_xml_doc`, `parse_xml_doc`, `add_section`, `update_section_body`, `update_section_refs`, `_find_section` all become tree-aware. `get_section_slugs` renamed to `get_section_paths` (returns slash-separated paths). New `walk_sections` helper for flat iteration |
| `write-section.py` | State format supports nested sections. `--parent` flag for child section emission. Finalize builds recursive XML. Merge mode (`--merge` and `parse_existing_sections()`) updated to handle nested sections — splits on all heading levels, matches by path |
| `assemble-markdown.py` | Recursive depth-first concatenation of section bodies |
| `verify-xml-refs.py` | Recursive section iteration. Finding `"section"` field uses slash-separated paths |
| `extract-edit-xml.py` | Extracts sections at any tree depth. Edit files are small |
| `merge-edit-xml.py` | Merges back to correct tree position using section path |
| `sync-edits-to-xml.py` | Splits markdown on markers, reconstructs tree from heading levels |
| `prepare-prose-verify.py` | Recursively iterates nested sections for prose verification input |
| `load-audit-findings.py` | Handles slash-separated section paths in findings |
| `schema.md` | Updated XML examples and ref type documentation |
| Section markers | `<!-- section: slug -->` at every heading level |
| Writer agents | Only current-format agents updated: `devops-writer.md`, `glossary-writer.md`, `overview-writer.md`. Emit per-heading via `write-section.py` instead of per-`##` |
| All test files | Updated for nested structure |

### What does NOT get built

- **Migration tool** — old XML files are regenerated from scratch
- **Depth-specific marker variants** — no `<!-- section-3: slug -->`, same marker everywhere
- **Content restructuring** — the writer doesn't add or remove headings; it writes the same markdown
- **Stale writer modernization** — `end-user-writer.md`, `developer-writer.md`, and `agent-writer.md` are not on the current format and are not updated for nested emission; they need a separate format update first

## Verification

1. **Round-trip fidelity**: `build_xml_doc` → `serialize_xml_doc` → `parse_xml_doc` produces identical nested structure at any depth. Parameterized test with 1, 2, 3 levels of nesting.

2. **Heading-level coverage**: For a document with `##`, `###`, `####` headings, verify each heading produces its own `<section>` at the correct nesting depth in the XML tree.

3. **Body isolation**: For a parent section with children, verify the parent's `<body>` contains only intro text — no child heading content leaks into it.

4. **Ref precision**: For a section tree with known refs split across children, verify each ref lives only in the `<section>` whose `<body>` mentions it.

5. **Edit extraction size**: Compare edit XML token count for old (flat) vs new (nested) model on the same group of findings. Expect >50% reduction for multi-subsection groups.

6. **Audit convergence**: Run audit→fix→audit on road-runner with the new model. Expect fewer new findings introduced by the fix step (smaller bodies constrain agent scope creep).

7. **Slash-path resolution**: Verify that `extract-edit-xml.py` and `merge-edit-xml.py` correctly resolve slash-separated section paths to the right tree nodes.
