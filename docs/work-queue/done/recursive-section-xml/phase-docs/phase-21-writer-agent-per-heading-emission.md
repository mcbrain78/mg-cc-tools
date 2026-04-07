# Phase 21: Writer Agent Per-Heading Emission

> Source: docs/work-queue/todo/recursive-section-xml/concept.md
> Phase goal: Writer agent prompts emit per-heading sections via write-section.py with `--parent`, section markers appear at every heading level, and end-to-end verification confirms round-trip fidelity and ref precision
> Requirements: TBD

---

## Writer Changes

The writer's prose output does not change — it still writes the same markdown with the same headings. The emission granularity changes: instead of one `write-section.py` call per `##` heading, the writer calls it once for the `##` intro and once for each `###`, `####`, etc. heading within that section.

Each call emits a small body (5-40 lines) with precisely scoped `typed_refs`. The writer knows exactly which entities it referenced because it just wrote about them — the ref-assignment problem shrinks from "which of 30 refs belong to this 200-line body" to "which refs did I just use in these 3 paragraphs."

Writer agent prompts (e.g., `devops-writer.md`) change from "for each `##` section, write content and call `write-section.py`" to "for each `##` section, write the intro and call `write-section.py`, then for each `###` heading write its content and call `write-section.py` with `--parent` set to the `##` slug, then for each `####` heading call with `--parent` set to the `##/###` path." The writer already processes sections sequentially from the template — this extends the existing loop to recurse into child headings.

## Design Decisions

### D6: Refs match body, always

*(Also relevant to Phase 18 core model — included here because writers must follow this rule)*

**Choice:** A section's `<refs>` declares exactly the entities mentioned in that section's `<body>` — no more, no less. If the same entity appears in both a parent's body and a child's body, both sections declare it. If it only appears in the child's body, only the child declares it.

**Why:** Each section is self-contained. Its refs describe what its body references. The audit checks each section's refs against its own body independently. A ref in a parent's `<refs>` that only appears in a child's body (not the parent's intro) correctly fails the parent's audit — the fix is to remove it from the parent's refs.

**Alternatives rejected:** "Refs only at deepest mention" — breaks self-containment. Extracting a parent section for editing would show incomplete refs for its body.

### D8: Writer markdown output unchanged

**Choice:** The writer produces the same markdown prose with the same headings it does today. Only the emission granularity changes — finer-grained `write-section.py` calls.

**Why:** This is a structural change to the XML model, not a content directive. Whether a section should have more or fewer headings is a template/content decision independent of how the XML tracks them.

## Scope

| Area | Changes |
|------|---------|
| Section markers | `<!-- section: slug -->` at every heading level |
| Writer agents | Only current-format agents updated: `devops-writer.md`, `glossary-writer.md`, `overview-writer.md`. Emit per-heading via `write-section.py` instead of per-`##` |

### What does NOT get built

- **Stale writer modernization** — `end-user-writer.md`, `developer-writer.md`, and `agent-writer.md` are not on the current format and are not updated for nested emission; they need a separate format update first

## Verification

6. **Audit convergence**: Run audit->fix->audit on road-runner with the new model. Expect fewer new findings introduced by the fix step (smaller bodies constrain agent scope creep).

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
*Phase: 21-writer-agent-per-heading-emission*
*Date: 2026-04-01*
