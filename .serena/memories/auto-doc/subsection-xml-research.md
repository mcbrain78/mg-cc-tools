# Subsection-Level XML Architecture Research

Research compiled 2026-03-31 from auto-doc codebase analysis. For concept spec: section → subsection-level XML model.

## 1. WRITE-SECTION.PY STRUCTURE (State Accumulation)

**Location:** `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/write-section.py`

### State File Format
- **Function:** `section_write()` (lines 134-228)
- **State structure:** Nested by document, then section
  ```
  {
    "documents": {
      "<doc_name>": {
        "header": "<header_text>",
        "sections_order": ["section_slug_1", "section_slug_2"],
        "sections": {
          "section_slug": {
            "content": "<!-- section: slug -->\n## Heading\n\nBody text",
            "symbols": ["list", "of", "symbols"],
            "file_paths": ["list/of/paths.py"],
            "typed_refs": [{"type": "db", ...}, ...]
          }
        }
      }
    }
  }
  ```
- **State loaded/saved via:** `load_json()` / `save_json()` (atomic operations)
- **Section ordering:** Preserved in `sections_order` list

### Finalize Logic (`finalize()`, lines 255-432)
1. **Merge mode** (if `--merge` flag and doc exists):
   - Reads existing `.md` file
   - Calls `parse_existing_sections()` (line 242) to extract by `##` heading splits
   - Replaces matching sections, preserves unmodified ones
   - Appends new sections not in existing doc

2. **Standard assembly:**
   - Combines header + sections in `sections_order` order
   - Each section is `content` field from state

3. **Manifest generation:**
   - For each section: only entry if non-empty `symbols` or `file_paths`
   - Format: `manifest["documents"][doc_name][section_slug] = {"symbols": [...], "file_paths": [...]}`

4. **XML generation (if `--xml-dir` set):**
   - Calls `build_xml_doc()` for initial mode
   - Calls `update_section_body()` + `update_section_refs()` for merge mode
   - Writes to `{xml_dir}/{audience}/{doc_name}.xml`

### Section Marker Injection
- **Location:** `section_write()` line 150-154
- **Pattern:** `<!-- section: <slug> -->`
- **Behavior:** Prepended to content if not present
- **Purpose:** Stable slug identifier independent of heading text

### To Support Subsections:
Would need to:
1. Extend `sections_order` to tree structure (nested lists or parent-slug refs)
2. Change state format to allow subsection nesting within section dict
3. Modify `parse_existing_sections()` to handle `###` headings in addition to `##`
4. Update manifest generation to include subsection entries
5. Extend XML generation calls to handle subsection creation

---

## 2. XML DOC MODEL (lib/xml_doc.py)

**Location:** `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/lib/xml_doc.py`

### Current Structure
- **Root element:** `<document audience="..." diataxis="..."></document>`
- **Children:**
  - `<meta>`: Contains `<title>`, `<generated>`, `<header>` (CDATA)
  - `<section slug="...">`: Direct children of root (flat list, no nesting)
    - `<refs>`: Native XML ref elements (db, code, flow, env, config, enum)
    - `<body>`: CDATA with markdown (includes `<!-- section: slug -->` marker)

### Key Functions

**`build_xml_doc()` (lines 25-57)**
- Takes: `audience`, `diataxis`, `header`, `sections` list
- Creates flat section structure
- Each section gets empty `<refs>` element (populated later by `update_section_refs()`)

**`parse_xml_doc()` (lines 73-108)**
- Returns dict: `{"audience": str, "diataxis": str, "meta": {...}, "sections": [...]}`
- Section dict: `{"slug": str, "body": str, "refs": [parsed_refs]}`

**`serialize_xml_doc()` (lines 229-243)**
- Writes tree to file with declaration and pretty print

**Section mutation helpers:**
- `add_section()` (lines 303-319): Appends new `<section>` to root
- `update_section_body()` (lines 281-300): Replaces CDATA in existing section's `<body>`
- `update_section_refs()` (lines 250-278): Replaces/builds `<refs>` element
- `_find_section()` (lines 335-341): Lookup by slug (iterates root's section children)
- `get_section_slugs()` (lines 322-332): Returns list of all section slugs in order

**`_build_refs_xml()` (lines 344-368)**
- Groups flat refs by type (db, code, flow, env, config, enum)
- Builds nested XML: `<refs><db>..., <code>..., <flow>..., etc.</refs>`

### Current Limitations
1. **No nesting:** Sections are direct children of root, no subsection elements
2. **Slug-only lookup:** `_find_section()` does linear scan of root.findall("section")
3. **No subsection markers:** Body CDATA only has `<!-- section: slug -->`, not `<!-- subsection: ... -->`
4. **No subsection refs:** All refs belong to section level, no subsection-scoped refs

### To Support Subsections:
Would need to:
1. Change section structure from flat to tree: `<section><subsection>..., <subsection>...</section>`
2. Add subsection slug attributes: `<subsection slug="...">`
3. Add subsection `<refs>` and `<body>` elements
4. Extend `_find_section()` to accept path like "section_slug/subsection_slug" or separate lookup
5. Add `add_subsection()`, `update_subsection_body()`, `update_subsection_refs()`
6. Extend `parse_xml_doc()` to recursively parse subsections
7. Extend `get_section_slugs()` or create new `get_subsection_slugs()` function

---

## 3. TEMPLATES (Heading Depth)

**Examined:** `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/references/templates/devops/OPERATIONS.template.md` (lines 1-200)

### Current Heading Hierarchy
- **`#` (level 1):** Document title (e.g., "Operations Guide")
- **`##` (level 2):** Section headings (template defines 3-4 main sections)
  - Example sections: "Infrastructure Overview", "Deployment", "Service Management", "Configuration Reference"
- **`###` (level 3):** Subsection headings within EXAMPLE comments (not actual content yet)
  - Example subsections: "Deployment Topology", "External Dependencies", "Architecture Diagram", "Deploy", "Rollback", "Graceful Shutdown", "Log Rotation"
- **`####` (level 4):** Deeper subsections within examples (rare)

### Real Generated Docs

**Examined:**
- `/home/mcbrain/mg_projects/road-runner/docs/auto-doc/devops/TROUBLESHOOTING.md`
- `/home/mcbrain/mg_projects/road-runner/docs/auto-doc/devops/OPERATIONS.md`

**Current structure:**
- `#` (level 1): Document title
- `##` (level 2): Section (marked with `<!-- section: slug -->`)
  - Lines 7-8 in TROUBLESHOOTING: `<!-- section: quick-diagnosis -->\n## Quick Diagnosis`
  - Lines 101-103 in OPERATIONS: `<!-- section: deployment -->\n## Deployment`
- `###` (level 3): Subsection headings **within sections** (NOT marked, NOT tracked)
  - Lines 13, 36, 108 in TROUBLESHOOTING: `### Triage Decision Tree`, `### First Steps (Always)`, etc.
  - Lines 13, 23, 33, 83, 107 in OPERATIONS: `### Deployment Topology`, `### External Dependencies`, etc.

### Key Observation
The `###` headings **already exist in generated docs** but are:
- **Not separated from section body** — they're just markdown within `<body>` CDATA
- **Not marked with markers** — only `<!-- section: slug -->` exists, no `<!-- subsection: ... -->`
- **Not tracked in metadata** — no subsection entries in manifest or refs structure
- **Not separately verified** — audit and verification work only at section level

---

## 4. ASSEMBLE-MARKDOWN.PY (Reassembly)

**Location:** `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/assemble-markdown.py`

**Function:** `assemble()` (lines 22-43)
1. Parses XML via `parse_xml_doc()`
2. Collects header from `doc["meta"]["header"]`
3. Iterates sections, appends each `section["body"]` (stripped)
4. Joins with `"\n\n"` separator
5. Returns assembled markdown

**Current:** Works on section-level bodies. Each body already contains:
```
<!-- section: slug -->
## Heading

### Subsection 1
Content...

### Subsection 2
Content...
```

**To Support Subsections:**
Would need to:
1. Extend to parse subsections from XML
2. Either: extract subsection `<body>` separately and reconstruct hierarchy
3. Or: reconstruct from subsection slug markers similar to section markers

---

## 5. SECTION MARKERS (Usage and Extension)

**Current Pattern:**
- `<!-- section: <slug> -->` placed before `##` heading in markdown
- Regex pattern: `/^\<!--\s*section:\s*(\S+)\s*-->/` (multiline mode)
- Used in: `write-section.py` (injection), `sync-edits-to-xml.py` (parsing), various tests

**Location of marker logic:**
- **Injection:** `write-section.py:150-154` — prepends if not present
- **Parsing:** `sync-edits-to-xml.py:31-32` — regex to extract slug
- **Storage:** Preserved in CDATA body text in XML

**Extension to Subsections:**
Could use: `<!-- subsection: <slug> -->` pattern
- Would need separate regex: `/^\<!--\s*subsection:\s*(\S+)\s*-->/`
- Placed before `###` headings
- Could create hierarchical slugs: "section-slug/subsection-slug"

**Pattern Locations to Update:**
- `write-section.py`: Add subsection marker injection
- `sync-edits-to-xml.py`: Parse both section and subsection markers
- `parse_existing_sections()`: Extend to handle `###` splits (currently only `##`)

---

## 6. VERIFY-XML-REFS.PY (Verification Model)

**Location:** `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/verify-xml-refs.py`

**Current Approach:**
- **Function:** `verify_xml_file()` (lines 372-400)
- **Logic:** Iterate sections, then refs within each section
  ```python
  for section in doc["sections"]:
      slug = section["slug"]
      for ref in section["refs"]:
          # Check if ref exists in codebase
          if error:
              findings.append({...document..., section: slug, ...})
  ```

**Current Finding Structure:**
```python
{
  "document": str,
  "section": str,        # <- Section slug only
  "audience": str,
  "description": str,
  "suggestion": str
}
```

**To Support Subsections:**
Would need to:
1. Add `"subsection": str` field to finding (optional, null if section-level)
2. Extend iteration:
   ```python
   for section in doc["sections"]:
       for subsection in section.get("subsections", []):
           for ref in subsection["refs"]:
               # Check ref...
   ```
3. Update `_make_finding()` to accept subsection parameter
4. Update audit agents to handle subsection-level findings

---

## 7. EXISTING HEADING DEPTHS IN GENERATED DOCS

**Examined docs:**
1. TROUBLESHOOTING.md (lines 1-150):
   - `##` sections: "Quick Diagnosis" (line 8), "Common Issues" (line 94)
   - `###` subsections: "Triage Decision Tree" (13), "First Steps (Always)" (36), "Prefect Server Won't Start" (101), "Worker Won't Start" (148)

2. OPERATIONS.md (lines 1-200):
   - `##` sections: "Infrastructure Overview" (line 8), "Deployment" (line 102)
   - `###` subsections: "Deployment Topology" (13), "External Dependencies" (23), "Architecture Diagram" (33), "Database Schemas" (83), "Deploy" (107), "Rollback" (implied), etc.

### Depth Distribution
- **Level 1 (`#`):** 1 per document (title)
- **Level 2 (`##`):** 2-4 per document (main sections)
- **Level 3 (`###`):** 3-8 per section on average (subsections, e.g., "Deploy" vs "Rollback" within "Deployment" section)
- **Level 4+ (`####`):** Rare in generated docs (only in code blocks, lists, embedded examples)

### Depth Usage Patterns
- Level 3 subsections are **logically grouped** within level 2 sections
  - "Deployment" (##) contains "Deploy" (###) and "Rollback" (###)
  - "Infrastructure Overview" (##) contains "Deployment Topology" (###), "External Dependencies" (###), "Architecture Diagram" (###), "Database Schemas" (###)
- Subsections typically have **distinct `<refs>` needs**
  - "Deploy" subsection references different components than "Rollback"
  - "Deployment Topology" subsection has database/infrastructure refs
  - "Database Schemas" subsection has schema/migration refs

---

## IMPACT SUMMARY FOR SUBSECTION DESIGN

### Current (Section-Level) Model
- Section = basic unit of documentation
- All refs collected at section level
- All verification/audit at section level
- Manifest tracks only section-level metadata

### Proposed (Subsection-Level) Model
- Section = container for subsections
- Subsections = basic units with their own refs
- Verification/audit can be subsection-specific
- Manifest can track subsection-level metadata
- Markers: `<!-- section: ... -->` and `<!-- subsection: ... -->`

### Files Requiring Change (Priority Order)
1. **lib/xml_doc.py** — Core data model (highest impact)
2. **write-section.py** — State accumulation and assembly (state format change)
3. **assemble-markdown.py** — Markdown output generation
4. **verify-xml-refs.py** — Verification findings model
5. **sync-edits-to-xml.py** — Edit XML parsing (marker parsing)
6. **extract-edit-xml.py** — Edit XML extraction (would work on subsections)
7. **audit-fixer.md** agent — Now works on subsections instead of sections
8. All XML manipulation tests (test_xml_doc.py, test_write_section.py, etc.)

### Backward Compatibility Considerations
- Existing documents with flat sections could be auto-migrated (each section becomes section + single subsection)
- Or: support both section-only and section+subsection models simultaneously
- State file version bump recommended
