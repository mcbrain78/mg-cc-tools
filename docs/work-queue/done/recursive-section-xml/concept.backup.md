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

### Downstream Pipeline Changes

- **assemble-markdown.py**: Recursive depth-first concatenation — section body, then child section bodies in order.
- **verify-xml-refs.py**: Recursive iteration over nested sections. Each section's refs checked against its own body independently.
- **extract-edit-xml.py**: Extracts individual sections (at any depth) into edit files. Edit files shrink from 200 lines to 5-40 lines.
- **merge-edit-xml.py**: Merges back to the correct tree position using the section path.
- **sync-edits-to-xml.py**: Splits markdown on any heading level, not just `##`.
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

**Why:** The document author chose the heading structure. If they wrote a `####`, that's a meaningful boundary. Imposing an arbitrary cutoff would lose precision at exactly the points where the author decided to add structure. In practice `####` is rare and `#####` essentially nonexistent, so this costs nothing but eliminates a special case.

### D4: No backward compatibility layer

**Choice:** Clean cutover. Old flat-section XML files are regenerated, not migrated.

**Why:** Single-developer tool with controlled deployments. A compatibility layer would add complexity for zero users.

### D5: Slug uniqueness is within parent

**Choice:** Slugs must be unique among siblings, not globally. Navigation uses tree path (slash-separated).

**Why:** Mirrors markdown — two sections can have a `### Prerequisites` heading as long as they're under different parents. Global uniqueness would force artificial disambiguation.

### D6: Refs match body, always

**Choice:** If an entity is mentioned in a section's body, that section's `<refs>` declares it — even if a parent or child section also declares the same ref.

**Why:** Each section is self-contained. Its refs describe what its body references. Duplication across parent and child is correct, not redundant. The audit checks each section independently.

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
| `lib/xml_doc.py` | Recursive section model — `build_xml_doc`, `parse_xml_doc`, `add_section`, `update_section_body`, `update_section_refs`, `_find_section` all become tree-aware |
| `write-section.py` | State format supports nested sections. `--parent` flag for child section emission. Finalize builds recursive XML. `parse_existing_sections()` splits on all heading levels |
| `assemble-markdown.py` | Recursive depth-first concatenation of section bodies |
| `verify-xml-refs.py` | Recursive section iteration. Finding `"section"` field uses slash-separated paths |
| `extract-edit-xml.py` | Extracts sections at any tree depth. Edit files are small |
| `merge-edit-xml.py` | Merges back to correct tree position using section path |
| `sync-edits-to-xml.py` | Splits markdown on any heading level |
| `schema.md` | Updated XML examples and ref type documentation |
| Section markers | `<!-- section: slug -->` at every heading level |
| Writer agents | Emit per-heading via `write-section.py` instead of per-`##` |
| All test files | Updated for nested structure |

### What does NOT get built

- **Migration tool** — old XML files are regenerated from scratch
- **Depth-specific marker variants** — no `<!-- section-3: slug -->`, same marker everywhere
- **Content restructuring** — the writer doesn't add or remove headings; it writes the same markdown

## Verification

1. **Round-trip fidelity**: `build_xml_doc` → `serialize_xml_doc` → `parse_xml_doc` produces identical nested structure at any depth. Parameterized test with 1, 2, 3 levels of nesting.

2. **Heading-level coverage**: For a document with `##`, `###`, `####` headings, verify each heading produces its own `<section>` at the correct nesting depth in the XML tree.

3. **Body isolation**: For a parent section with children, verify the parent's `<body>` contains only intro text — no child heading content leaks into it.

4. **Ref precision**: For a section tree with known refs split across children, verify each ref lives only in the `<section>` whose `<body>` mentions it.

5. **Edit extraction size**: Compare edit XML token count for old (flat) vs new (nested) model on the same group of findings. Expect >50% reduction for multi-subsection groups.

6. **Audit convergence**: Run audit→fix→audit on road-runner with the new model. Expect fewer new findings introduced by the fix step (smaller bodies constrain agent scope creep).

7. **Slash-path resolution**: Verify that `extract-edit-xml.py` and `merge-edit-xml.py` correctly resolve slash-separated section paths to the right tree nodes.
