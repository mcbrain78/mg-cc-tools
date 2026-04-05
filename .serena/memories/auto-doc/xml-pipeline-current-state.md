# Auto-Doc XML Pipeline: Current State (Flat Section Model)

## Overview

The auto-doc XML pipeline is a sophisticated document lifecycle system for maintaining audience-specific documentation with typed code references. It operates on a **nested but flat-addressed** section model where documents contain sections at arbitrary nesting depth, all addressed by slash-separated paths.

**Key Architecture**: Write → Finalize (assemble & generate XML) → Verify refs → Prose verify → Audit findings → Fix queue (extract/edit/merge)

---

## 1. Section Model & XML Schema (xml_doc.py)

### Current Data Model

**State Format** (write-section.py state file): Hierarchical tree structure with subsections
```
documents:
  ARCHITECTURE:
    header: "..."
    sections_order: ["overview", "monitoring-alerting"]
    sections:
      overview:
        content: "..."
        symbols: [...]
        file_paths: [...]
        typed_refs: [...]
        subsections: {}
        subsections_order: []
      monitoring-alerting:
        content: "..."
        symbols: [...]
        file_paths: [...]
        typed_refs: [...]
        subsections:
          health-artifact:
            content: "..."
            symbols: [...]
            file_paths: [...]
            typed_refs: [...]
            subsections: {}
            subsections_order: []
        subsections_order: ["health-artifact"]
```

**XML Schema** (nested with CDATA bodies):
```xml
<document audience="devops" diataxis="how-to">
  <meta>
    <title>...</title>
    <generated>2024-04-05</generated>
    <header><![CDATA[<!-- DIATAXIS: how-to -->...]]></header>
  </meta>
  <section slug="overview">
    <refs>
      <code>
        <class name="Handler"/>
      </code>
    </refs>
    <body><![CDATA[<!-- section: overview -->## Overview
...content...]]></body>
  </section>
  <section slug="monitoring-alerting">
    <refs>...</refs>
    <body><![CDATA[<!-- section: monitoring-alerting -->## Monitoring & Alerting
...content...]]></body>
    <section slug="health-artifact">
      <refs>...</refs>
      <body><![CDATA[<!-- section: health-artifact -->### Health Artifact
...content...]]></body>
    </section>
  </section>
</document>
```

### Section Addressing

- **Top-level**: Bare slugs (e.g., "overview", "monitoring-alerting")
- **Nested**: Slash-separated paths (e.g., "monitoring-alerting/health-artifact")
- **Deep nesting**: e.g., "monitoring-alerting/health-artifact/artifact-format"

Navigation functions:
- `_find_section_by_path(root, path)` — returns XML element or None
- `_find_section(tree, path)` — returns element or raises ValueError
- `get_section_paths(tree)` — returns list of all paths (depth-first)
- `get_section_slugs(tree)` — returns top-level slug list (backward compat)
- `walk_sections(sections, prefix="")` — generator yielding (path, section_dict) tuples

### Ref Types (Typed References)

All stored as flat JSON in `typed_refs` arrays, organized in XML as nested elements:

**Code refs**: `{"type": "code", "kind": "class|function|variable", "name": "...", "module": "...", "attr": "...", "param": "..."}`
**DB refs**: `{"type": "db", "schema": "...", "table": "...", "column": "..."}`
**Flow refs**: `{"type": "flow", "name": "..."}`
**Env refs**: `{"type": "env", "name": "..."}`
**Config refs**: `{"type": "config", "path": "..."}`
**Enum refs**: `{"type": "enum", "class": "...", "field": "...", "value": "..."}`
**Dep refs**: `{"type": "dep", "name": "..."}`
**Literal refs**: `{"type": "literal", "name": "..."}`
**Ext refs**: `{"type": "ext", "name": "..."}`
**Malformed refs**: `{"type": "malformed", "original_type": "...", ...other fields as-is...}`

XML nested structure example:
```xml
<refs>
  <code>
    <class name="Handler">
      <attr>run_id</attr>
    </class>
    <function name="process" module="processor.py">
      <param>timeout</param>
    </function>
  </code>
  <db>
    <schema name="public">
      <table name="runs">
        <column>id</column>
        <column>status</column>
      </table>
    </schema>
  </db>
</refs>
```

---

## 2. Write Phase (write-section.py)

### Two Modes

**Section-write mode** (called once per section by writer agents):
```bash
write-section.py \
  --state-file /tmp/write-state-devops.json \
  --document ARCHITECTURE \
  --section system-overview \
  [--parent monitoring-alerting/health] \
  --content-file /tmp/section-devops-ARCHITECTURE-system-overview.md \
  --refs-file /tmp/refs-devops-ARCHITECTURE-system-overview.json \
  [--header-file /tmp/header-devops-ARCHITECTURE.md] \
  [--heading-state /tmp/heading-state-devops-ARCHITECTURE.json] \
  [--project-root /path/to/project]
```

**Finalize mode** (called once after all writers complete):
```bash
write-section.py \
  --finalize \
  --state-file /tmp/write-state-devops.json \
  --docs-dir /path/to/docs \
  --audience devops \
  --manifest-file /tmp/manifest-devops.json \
  [--merge] \
  [--xml-dir /path/to/xml-sources]
```

### Section-Write Workflow

1. Load state file (create if missing)
2. Read content-file (validate non-empty)
3. Inject `<!-- section: {slug} -->` marker if missing
4. Read refs-file (must contain `typed_refs` key)
5. Optionally read header-file (stored in doc metadata)
6. Parse `typed_refs`, discharge malformed refs
7. Derive `symbols` and `file_paths` from typed_refs
8. Build section entry with subsections keys (preserves nested children on update)
9. If parent_path given: walk state tree to find parent, add as subsection
10. Otherwise: add to top-level sections dict
11. Advisory symbol check (warnings on stderr, no exit code impact)
12. Save state atomically

### Finalize Workflow

1. Load state file
2. For each document:
   - Assemble markdown from state tree (depth-first traversal)
   - If merge mode + existing doc exists: replace/append sections, preserve unmodified
   - Write markdown to `{docs_dir}/{audience}/{DOCUMENT}.md`
3. Build manifest (references deduplication):
   - Recursively collect sections with non-empty refs
   - Entry format: `{section_path}: {"symbols": [...], "file_paths": [...]}`
   - In initial mode: add `_written_sections` metadata (all paths written)
4. Write manifest atomically
5. If `--xml-dir` provided: build/merge XML files
   - Initial mode: build new XML from scratch using nested structure
   - Merge mode: update existing XML sections in place
   - Populate `<refs>` from typed_refs at correct paths
6. Print summary to stderr

### State Tree → XML Conversion

Function `_state_sections_to_xml(doc_data)`:
- Recursively converts state document tree to list of section dicts for `build_xml_doc`
- Each section dict has: `slug`, `body`, `children` (list of nested section dicts)
- `build_xml_doc` creates `<section>` elements with nested structure matching the tree

---

## 3. Ref Extraction & Discharge (ref_validation.py, typed_refs format)

### Discharge Process (write-section.py line 249)

`discharge_malformed_refs(typed_refs)`:
- Filters out incomplete refs (missing required identifier fields)
- Moves problematic refs to "malformed" type with original_type + all fields preserved
- Defense-in-depth: prepare-prose-verify.py also skips malformed when formatting

### Typed Ref Format Location
- `references/typed-refs-format.md` — documented format for all ref types

---

## 4. Markdown Assembly (assemble-markdown.py)

Reads XML source document:
1. Extract header CDATA from `<meta><header>`
2. Walk sections depth-first via `walk_sections(doc["sections"])`
3. Concatenate header + all section bodies (CDATA unescaped)
4. Write to output .md file

The `<!-- section: slug -->` markers and heading lines are embedded in CDATA, so they pass through unchanged.

---

## 5. Sync Edits Back to XML (sync-edits-to-xml.py)

For marking-based sync workflow (human markdown editing):

1. **Split on markers**: `<!-- section: slug -->` markers
2. **Infer paths**: Use heading levels (## = level 2, ### = level 3, etc.) to reconstruct hierarchy
   - Stack-based path inference: pop stack while top's depth >= current, build path from stack + current slug
3. **Match & update**: For each inferred path in md file, find corresponding XML section, compare bodies
4. **Serialize**: Write changes back to XML atomically
5. Return changed paths (for targeted ref re-extraction)

---

## 6. Edit Group Extraction & Merging (extract-edit-xml.py, merge-edit-xml.py)

### Extract Phase

Input: grouping JSON + findings array + xml-dir
Output: per-group edit XML with only relevant sections

1. Load grouping file (contains groups with finding_indices)
2. Build XML index: (audience, document) → xml_path
3. Group findings by (xml_path, section_path)
4. For each info:
   - Parse master XML (cached)
   - Find section via `_find_section_by_path(root, section_path)`
   - Create edit section with attributes: source, slug (leaf), path (full), audience, document
   - Copy findings (read-only context)
   - Deep-copy refs from master (preserves native XML structure)
   - Copy body CDATA from master

Edit XML structure:
```xml
<edit-group id="group-0">
  <summary>Root cause summary...</summary>
  <section source="/path/to/OPERATIONS.xml" slug="deployment-topology" 
           path="infrastructure-overview/deployment-topology" 
           audience="devops" document="OPERATIONS">
    <findings>
      <finding check="prose-refs">Description...</finding>
    </findings>
    <refs>...</refs>
    <body><![CDATA[...]]></body>
  </section>
</edit-group>
```

### Merge Phase

Input: edit XML (modified by fixer agent)
Output: updated master XML files + JSON summary

1. Parse edit XML
2. For each section in edit:
   - Get source (absolute path to master XML)
   - Get path (slash-separated)
   - Parse master XML (cached)
   - Find master section via path
   - Extract edit body + refs
   - Compare with master
   - If changed: call `update_section_body(tree, path, new_body)` and/or `update_section_refs(tree, path, refs)`
3. Serialize changed masters atomically
4. Return summary: files_modified, sections_updated, errors

---

## 7. Prose Verification Prep (prepare-prose-verify.py)

Extracts per-section (body, refs_as_text) pairs for LLM prose-vs-refs verification:

1. Parse XML document
2. Walk sections depth-first
3. Format refs as human-readable bullet list via `format_refs_as_text(refs)`
4. Write per-section JSON files in nested directories:
   - Path structure: `{output_dir}/{section_path}.json`
   - Each file contains: path, slug, document, audience, body, refs_as_text, malformed_refs
5. Write manifest.json listing all section paths

Example formatted refs:
```
- [code:class] Handler in processor.py
- [db] public.runs.id
- [flow] etl_job
- [config] .env
```

---

## 8. Ref Verification (verify-xml-refs.py)

Deterministic verification of typed refs against codebase:

**SourceCache class**: Lazy-loading cache for AST analysis
- `get_symbols(rel_path)` — extracted symbols from Python files
- `get_signatures(rel_path)` — function signatures
- `get_sqla_models(rel_path)` — SQLAlchemy model extraction
- `get_class_attrs(rel_path, class_name)` — class attributes
- `get_enum_values(rel_path, class_name)` — enum field values
- `get_decorated_functions(rel_path, decorator)` — @flow, etc.
- `get_pyproject_deps()` — project dependencies from pyproject.toml

Walks XML documents and sections, verifies each typed ref against source files. Appends findings to findings file atomically. Exit 0 always (findings are data, not errors).

---

## 9. Audit Findings & Fix Queue (load-audit-findings.py, fix-queue.py)

### Load & Merge

Reads deterministic audit findings + prose findings, deduplicates by (document, section, check, description).

### Fix Queue

Script-controlled sequential processing of approved groups:

**init subcommand**: Create state file with queue of group indices
**next subcommand**: Loop management
1. Merge previous group (if current is set)
   - Generate unified diff: original extraction vs agent-edited
   - Run merge-edit-xml.py
   - Move to completed list
2. Extract next group from queue
   - Run extract-edit-xml.py
   - Save original .xml for diffing
   - Count sections
   - If 0 sections: skip, continue to next
   - If sections found: set as current, return JSON status
3. If queue exhausted: return done status

State file tracks: config, queue, current, completed, skipped, files_modified, diffs

---

## 10. Writer Agent Integration

All writer agents (devops-writer, developer-writer, etc.) follow this pattern:

1. **Receive headings one at a time** from `next-heading.py`
   - Each response: type (orient|write|done), heading_outline, source_files (for orient), section_slug + parent_path + purpose + example (for write)
2. **Orient phase**: Read source files to gather context
3. **Write phase**: Generate section content
   - Write content file (no heading lines — injected by write-section.py)
   - Write refs file with typed_refs for entities mentioned in this section
   - Call write-section.py with --parent if nested
   - Pass --heading-state for deterministic heading injection
   - Pass --header-file only on first section of document
4. **Done**: Loop exits when done=true

Example call (from devops-writer.md):
```bash
python3 write-section.py \
  --state-file /tmp/write-state-devops-OPERATIONS.json \
  --document OPERATIONS \
  --section required-variables \
  --parent config-reference/environment-variables \
  --content-file /tmp/section-devops-OPERATIONS-config-reference-environment-variables-required-variables.md \
  --refs-file /tmp/refs-devops-OPERATIONS-config-reference-environment-variables-required-variables.json \
  --heading-state /tmp/heading-state-devops-OPERATIONS.json \
  --project-root /path/to/project
```

**Refs scoping rule**: Emit refs ONLY for entities mentioned in current section, not children. Child refs belong in child's refs file.

---

## 11. Key Functions & Interfaces

### xml_doc.py

**Build**:
- `build_xml_doc(audience, diataxis, header, sections, title=None)` → ElementTree

**Parse**:
- `parse_xml_doc(path)` → dict with audience, diataxis, meta, sections (nested)

**Serialize**:
- `serialize_xml_doc(tree, path)` → atomic write

**Navigation**:
- `_find_section_by_path(root, path)` → element or None
- `_find_section(tree, path)` → element or ValueError
- `get_section_paths(tree)` → list[str]
- `get_section_slugs(tree)` → list[str] (top-level only)
- `walk_sections(sections, prefix="")` → generator of (path, section_dict)

**Mutation**:
- `update_section_body(tree, path, new_body)` → tree
- `update_section_refs(tree, path, flat_refs)` → tree
- `add_section(tree, slug, body, parent_path=None)` → tree

### write-section.py

**CLI**:
- Section-write mode: --state-file, --document, --section, --content-file, --refs-file, [--parent], [--header-file], [--heading-state], [--project-root]
- Finalize mode: --finalize, --state-file, --docs-dir, --audience, --manifest-file, [--merge], [--xml-dir]

**Helper functions**:
- `parse_existing_sections(content)` → (header, [(path, heading_line, body)])
- `_state_sections_to_xml(doc_data)` → list of section dicts for build_xml_doc
- `_collect_all_sections_depth_first(sections, order, prefix)` → list of (path, section) tuples
- `_collect_manifest_entries(sections, order, prefix)` → generator of (path, symbols, file_paths)

---

## 12. Known Limitations & Quirks

1. **Flat marker-based addressing**: Despite nested XML structure, sections are all addressed by slash-separated paths. No tree navigation during merge.
2. **State tree complexity**: write-section.py maintains hierarchical state with subsections_order and subsections dicts at each level. Hard to reason about nesting rules.
3. **Heading injection timing**: next-heading.py manages heading state; write-section.py injects deterministically. Requires two-file coordination.
4. **Marker-based split fragility**: sync-edits-to-xml.py splits on `<!-- section: slug -->` markers; heading level inference is heuristic-based (can break with atypical formatting).
5. **Edit group scoping**: extract-edit-xml.py matches findings to sections but only copies the section itself, not context about parent/child relationships.
6. **Ref discharge timing**: Happens at write time, not extraction time. Early refs may have malformed, later refs may be clean.
7. **Manifest duplication**: sections_order and _written_sections metadata both track written sections (slightly different representations).

---

## 13. Data Flow Summary

```
Writer Agents
  ↓ (content + typed_refs files)
write-section.py (section-write mode)
  ↓ (accumulates in state file)
State file (hierarchical tree)
  ↓
write-section.py (finalize mode)
  ↓ (both paths)
  ├→ Markdown assembly + write to {docs_dir}/{audience}/{DOC}.md
  └→ XML build/merge + write to {xml_dir}/{audience}/{DOC}.xml
       ├→ (nested sections structure)
       └→ (typed refs grouped in <refs>)
       
XML Sources
  ↓ (for audit)
verify-xml-refs.py
  ↓ (ref verification findings)
Audit findings
  ↓
load-audit-findings.py (merge + deduplicate)
  ↓
fix-queue.py (init + next loop)
  ├→ extract-edit-xml.py (per group)
  │  ↓ (edit XML with findings context)
  │  Fixer agent (Edit tool)
  │  ↓ (modified edit XML)
  └→ merge-edit-xml.py (merge back)
     ↓ (updated master XMLs)
     serialize_xml_doc (atomic write)
```

---

## 14. Configuration References

- `docs_dir`: Output directory for assembled markdown files
- `audiences.{audience}.documents`: List of document names for that audience
- `templates_dir`: Directory containing refined templates (read by next-heading.py)

Writer agents receive these as arguments from orchestrator agents.
