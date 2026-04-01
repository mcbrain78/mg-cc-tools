# Phase 19: Nested Write-Section & Assembly

> Source: docs/work-queue/todo/recursive-section-xml/concept.md
> Phase goal: write-section.py supports `--parent` flag for hierarchical child section emission with nested state format and recursive XML finalization, and assemble-markdown.py concatenates sections depth-first
> Requirements: TBD

---

## write-section.py CLI Interface

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

## write-section.py State Format

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

## Downstream Pipeline Changes (assemble-markdown.py)

- **assemble-markdown.py**: Recursive depth-first concatenation — section body, then child section bodies in order.

## Design Decisions

### D4: No backward compatibility layer

**Choice:** Clean cutover for the structural migration. Old flat-section XML files are regenerated, not migrated. No code that reads both old and new formats.

**Why:** Single-developer tool with controlled deployments. A compatibility layer would add complexity for zero users.

**Note:** This covers the migration from flat to nested XML. The `--merge` flag in `write-section.py` (used by the update pipeline for incremental section updates) is a separate concern — it is updated for the nested model, not removed.

## Scope

| Area | Changes |
|------|---------|
| `write-section.py` | State format supports nested sections. `--parent` flag for child section emission. Finalize builds recursive XML. Merge mode (`--merge` and `parse_existing_sections()`) updated to handle nested sections — splits on all heading levels, matches by path |
| `assemble-markdown.py` | Recursive depth-first concatenation of section bodies |

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
*Phase: 19-nested-write-section-assembly*
*Date: 2026-04-01*
