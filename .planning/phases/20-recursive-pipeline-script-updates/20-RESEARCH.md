# Phase 20: Recursive Pipeline Script Updates - Research

**Researched:** 2026-04-01
**Domain:** Python script migration from flat section iteration to recursive tree traversal
**Confidence:** HIGH

## Summary

Phase 20 updates six downstream pipeline scripts to work with the recursive XML section model built in Phase 18 and extended in Phase 19. The core transformation is consistent across all scripts: replace flat `doc["sections"]` iteration and `findall("section")` lookups with recursive `walk_sections()` traversal and `_find_section_by_path()` navigation. The finding JSON format changes from bare slugs to slash-separated paths in the `"section"` field.

The xml_doc.py module already provides all needed primitives (`walk_sections`, `_find_section_by_path`, `_find_section`, `get_section_paths`). The mutation helpers (`update_section_body`, `update_section_refs`) already accept slash-separated paths since Phase 18. This phase is purely about the consumer scripts adopting these primitives.

The most complex script is sync-edits-to-xml.py which must reconstruct tree hierarchy from heading levels in flat markdown. The simplest is load-audit-findings.py which only needs to handle slash-separated paths in its deduplication key (no structural changes). All other scripts follow a predictable pattern of replacing flat loops with `walk_sections()` or `_find_section_by_path()`.

**Primary recommendation:** Group scripts by complexity -- batch the straightforward walk_sections conversions (verify-xml-refs, prepare-prose-verify, load-audit-findings) separately from the extract/merge pair and the sync script which have more intricate changes.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Findings use a single `"section"` field with slash-separated paths: `"monitoring-alerting/etl-run-logging"` (D7)
- No separate fields per depth level -- one field works at any depth
- Leaf slug: `path.rsplit("/", 1)[-1]`; parent path: `path.rsplit("/", 1)[0]`
- All scripts use `_find_section_by_path()` from xml_doc.py (built in Phase 18) to locate sections in the XML tree
- Replaces current flat `findall("section")` lookups
- Path resolution relies on sibling slug uniqueness (D5)
- verify-xml-refs.py: recursive iteration, finding `"section"` field uses slash-separated paths, parent's ref failing parent's audit
- prepare-prose-verify.py: recursively iterates, output files use nested directories mirroring tree
- extract-edit-xml.py: uses `_find_section_by_path()`, `<edit-group>` XML adds `path` attribute alongside `slug`
- merge-edit-xml.py: uses `path` attribute from edit-group XML with `_find_section_by_path()`
- sync-edits-to-xml.py: flat split by marker then heading-level reconstruction; heading level is authoritative for tree position
- load-audit-findings.py: handles slash-separated section paths, no structural changes beyond path format

### Claude's Discretion
- Error handling when `_find_section_by_path` returns None (section not found in tree)
- How sync-edits-to-xml.py handles malformed heading hierarchies (e.g., `####` directly under `##` with no `###`)
- Whether prepare-prose-verify.py creates nested directories eagerly or lazily
- Test organization -- whether to test scripts individually or with shared fixtures for the nested XML tree
- Whether extract-edit-xml.py validates that the `path` attribute matches the actual tree position

### Deferred Ideas (OUT OF SCOPE)
- Writer agent prompt changes for per-heading emission -- Phase 21
- End-to-end audit convergence verification on road-runner -- Phase 21
- Stale writer modernization -- separate effort
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RPS-01 | Findings identify their section using a single `"section"` field containing a slash-separated path that addresses sections at any tree depth | `_make_finding()` in verify-xml-refs.py and finding dicts in all scripts change from bare slug to path from `walk_sections()` |
| RPS-02 | Reference verification recursively visits nested sections and audits each section's refs against its own body independently | `verify_xml_file()` changes from `for section in doc["sections"]` to `for path, section in walk_sections(doc["sections"])` |
| RPS-03 | Prose verification input is produced for every section in the tree, with output files in nested directories | `prepare()` uses `walk_sections()` and `os.makedirs()` for nested output dirs mirroring section hierarchy |
| RPS-04 | Section extraction produces edit-group XML with `path` attribute on `<section>` elements | `extract_edit_xml()` uses `_find_section_by_path()` instead of flat `findall("section")`, adds `path=` attribute |
| RPS-05 | Edit merging uses the `path` attribute to locate target node and merge to correct tree position | `merge_edit_xml()` reads `path` attribute, uses `_find_section_by_path()` instead of flat slug lookup |
| RPS-06 | Markdown-to-XML sync reconstructs section tree from heading levels | `sync()` adds heading-level parsing to reconstruct nesting after flat marker split |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lxml | (installed) | XML parsing, CDATA, tree manipulation | Already used by all scripts via xml_doc.py |
| lib/xml_doc.py | Phase 18+ | `walk_sections`, `_find_section_by_path`, `_find_section`, `parse_xml_doc` | Single source of truth for recursive navigation |
| lib/json_io.py | existing | `load_json`, `save_json` atomic I/O | Established project pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| os.makedirs | stdlib | Nested directory creation | prepare-prose-verify.py nested output dirs |
| re (existing) | stdlib | Heading level extraction, section markers | sync-edits-to-xml.py heading depth detection |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `walk_sections()` | Manual recursive `_parse_section` walk | Duplicates existing tested primitive |
| Heading-level regex | lxml/markdown AST parsing | Over-engineered for `##`/`###`/`####` counting |

## Architecture Patterns

### Pattern 1: Flat-to-Recursive Loop Migration
**What:** Replace `for section in doc["sections"]` with `for path, section in walk_sections(doc["sections"])`.
**When to use:** Every script that iterates all sections (verify-xml-refs, prepare-prose-verify).
**Example:**
```python
# BEFORE (flat):
for section in doc["sections"]:
    slug = section["slug"]
    # ... process section using slug as identifier

# AFTER (recursive):
from lib.xml_doc import walk_sections
for path, section in walk_sections(doc["sections"]):
    # path = "monitoring-alerting/etl-run-logging" for nested
    # path = "deployment" for top-level (backward compatible)
    # ... process section using path as identifier
```

### Pattern 2: Flat XML Lookup to Path-Based Navigation
**What:** Replace `findall("section")` + slug match with `_find_section_by_path()`.
**When to use:** extract-edit-xml.py, merge-edit-xml.py -- anywhere a specific section must be located in the XML tree.
**Example:**
```python
# BEFORE (flat):
for el in master_tree.getroot().findall("section"):
    if el.get("slug") == slug:
        section_el = el
        break

# AFTER (path-based):
from lib.xml_doc import _find_section_by_path
section_el = _find_section_by_path(master_tree.getroot(), path)
if section_el is None:
    # handle missing section
    continue
```

### Pattern 3: Nested Directory Mirroring
**What:** Output files mirror the section tree as nested directories.
**When to use:** prepare-prose-verify.py output organization.
**Example:**
```python
# path = "monitoring-alerting/etl-run-logging"
# output_dir/monitoring-alerting/etl-run-logging.json
leaf_slug = path.rsplit("/", 1)[-1]
parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
file_dir = os.path.join(output_dir, parent_path) if parent_path else output_dir
os.makedirs(file_dir, exist_ok=True)
section_path = os.path.join(file_dir, f"{leaf_slug}.json")
```

### Pattern 4: Heading-Level Tree Reconstruction
**What:** After flat split by `<!-- section: slug -->` markers, reconstruct nesting from heading levels.
**When to use:** sync-edits-to-xml.py only.
**Example:**
```python
# Input: flat list of (slug, body) from marker split
# Output: list of (path, body) with full slash-separated paths
#
# "## Monitoring"     -> heading level 2 -> depth 0 -> path "monitoring-alerting"
# "### ETL Logging"   -> heading level 3 -> depth 1 -> path "monitoring-alerting/etl-run-logging"
# "### Alert Routing"  -> heading level 3 -> depth 1 -> path "monitoring-alerting/alert-routing"
# "## Deployment"     -> heading level 2 -> depth 0 -> path "deployment"
```

### Pattern 5: Edit-Group XML Path Attribute
**What:** Add `path` attribute to `<section>` elements in edit-group XML, retain `slug` for display.
**When to use:** extract-edit-xml.py output and merge-edit-xml.py input.
**Example:**
```xml
<edit-group id="tracking-funcs">
  <summary>Tracking functions not named</summary>
  <section source="/path/to/OPS.xml"
           slug="etl-run-logging"
           path="monitoring-alerting/etl-run-logging"
           audience="devops"
           document="OPS">
    <findings>...</findings>
    <refs>...</refs>
    <body><![CDATA[...]]></body>
  </section>
</edit-group>
```

### Anti-Patterns to Avoid
- **Iterating only top-level sections:** All scripts must use `walk_sections()` or recursive traversal, never `doc["sections"]` alone which misses children.
- **Building paths manually:** Use `walk_sections()` which yields the correct slash-separated path -- do not manually reconstruct paths from slug chains.
- **Assuming fixed depth:** Scripts must handle 1-3+ levels of nesting. Never hardcode depth assumptions.
- **Breaking the round-trip:** The extract-edit-xml -> merge-edit-xml round-trip must remain idempotent when no edits are made.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Recursive section traversal | Manual recursive walk | `walk_sections()` from xml_doc.py | Already tested in Phase 18, yields (path, section) tuples |
| Path-based XML node lookup | Manual nested findall loop | `_find_section_by_path()` from xml_doc.py | Handles arbitrary depth, returns None on miss |
| Mandatory section lookup | Path lookup + manual ValueError | `_find_section()` from xml_doc.py | Wraps `_find_section_by_path` with ValueError on miss |
| Section path enumeration | Manual tree walk collecting paths | `get_section_paths()` from xml_doc.py | Returns depth-first ordered list |

**Key insight:** Phase 18 built all the navigation primitives specifically so Phase 20 scripts can be thin consumers. The work is replacing call sites, not building new infrastructure.

## Common Pitfalls

### Pitfall 1: Finding `group_id` Format Change
**What goes wrong:** The `_make_finding()` in verify-xml-refs.py constructs `group_id` from `f"{document}/{section}"`. When `section` becomes a path like `"monitoring-alerting/etl-run-logging"`, the group_id becomes `"OPS/monitoring-alerting/etl-run-logging"` which still works but changes format.
**Why it happens:** `group_id` is derived from section identifier, which changes from slug to path.
**How to avoid:** Accept the format change -- it remains a unique string. Verify that downstream consumers (grouping agent) handle multi-slash group_ids.
**Warning signs:** Grouping agent tests failing on path-containing group_ids.

### Pitfall 2: Flat Section Lookup in merge-edit-xml.py
**What goes wrong:** Current merge-edit-xml.py uses `findall("section")` on master root to find by slug. This only searches top-level. With nested sections, a child section won't be found.
**Why it happens:** `findall("section")` only returns direct children, not descendants.
**How to avoid:** Switch to `_find_section_by_path(master_tree.getroot(), path)`. The `path` attribute from edit XML is the key lookup field, not `slug`.
**Warning signs:** "Section not found" errors for nested sections that definitely exist.

### Pitfall 3: update_section_body/update_section_refs Already Accept Paths
**What goes wrong:** Developer might add path-resolution logic to merge-edit-xml.py not realizing the mutation helpers already handle it.
**Why it happens:** Phase 18 already updated `update_section_body` and `update_section_refs` to use `_find_section()` which accepts slash-separated paths.
**How to avoid:** Just pass the path string directly to `update_section_body(tree, path, body)`. No additional lookup needed.
**Warning signs:** Redundant `_find_section_by_path` calls before mutation helper calls.

### Pitfall 4: sync-edits-to-xml.py Heading Level Edge Cases
**What goes wrong:** Heading-level reconstruction breaks on malformed hierarchies like `####` directly under `##` (skipping `###`).
**Why it happens:** Real markdown may have inconsistent heading levels from manual editing.
**How to avoid:** Treat any heading deeper than current as a child, regardless of exact level gap. A `####` under `##` becomes a child of the `##` section. The stack-based approach handles this naturally: push on deeper, pop on same-or-shallower.
**Warning signs:** Sections at wrong tree position or orphaned sections.

### Pitfall 5: prepare-prose-verify.py Manifest Format Change
**What goes wrong:** Manifest currently lists slugs. With nested output, manifest should list paths for downstream consumers to locate files.
**Why it happens:** Manifest needs to match the actual file organization.
**How to avoid:** Change manifest `"sections"` from slug list to path list. Paths encode the directory structure (e.g., `"monitoring-alerting/etl-run-logging"`).
**Warning signs:** Downstream prose verification step can't find section JSON files.

### Pitfall 6: extract-edit-xml.py Section Finding Uses Slug from Finding
**What goes wrong:** Current code uses `f.get("section", "")` which was a bare slug. It looks up via flat `findall("section")`. Both need to change.
**Why it happens:** The finding's `"section"` field now contains a path, and the lookup must be path-based.
**How to avoid:** Use the finding's `"section"` value (now a path) with `_find_section_by_path()`.
**Warning signs:** Nested sections not found during extraction.

## Code Examples

### verify-xml-refs.py: Recursive Section Iteration
```python
# Source: Current codebase + xml_doc.py walk_sections pattern
from lib.xml_doc import parse_xml_doc, walk_sections

def verify_xml_file(xml_path, cache):
    doc = parse_xml_doc(xml_path)
    audience = doc["audience"]
    doc_name = _doc_name_from_path(xml_path)

    findings = []
    for path, section in walk_sections(doc["sections"]):
        for ref in section["refs"]:
            ref_type = ref.get("type", "")
            checker = CHECKER_BY_TYPE.get(ref_type)
            if not checker:
                continue
            error = checker(ref, cache)
            if error:
                findings.append(_make_finding(
                    document=doc_name,
                    section=path,  # was: slug
                    audience=audience,
                    description=error,
                    suggestion=_suggestion_for_type(ref_type),
                ))
    return findings
```

### prepare-prose-verify.py: Nested Directory Output
```python
# Source: Current codebase + walk_sections pattern
from lib.xml_doc import parse_xml_doc, walk_sections

def prepare(xml_path, output_dir):
    doc = parse_xml_doc(xml_path)
    doc_name = os.path.splitext(os.path.basename(xml_path))[0]
    os.makedirs(output_dir, exist_ok=True)

    paths = []
    for path, section in walk_sections(doc["sections"]):
        body = section["body"]
        refs_text = format_refs_as_text(section["refs"])
        slug = section["slug"]

        section_data = {
            "path": path,
            "slug": slug,
            "document": doc_name,
            "audience": doc["audience"],
            "body": body,
            "refs_as_text": refs_text,
        }

        # Nested directory structure: monitoring-alerting/etl-run-logging.json
        parent_dir = os.path.join(output_dir, os.path.dirname(path))
        os.makedirs(parent_dir, exist_ok=True)
        file_name = f"{slug}.json"
        save_json(os.path.join(parent_dir, file_name), section_data)
        paths.append(path)

    # Manifest lists paths (not just slugs)
    manifest = {
        "xml_file": xml_path,
        "audience": doc["audience"],
        "document": doc_name,
        "sections": paths,
    }
    save_json(os.path.join(output_dir, "manifest.json"), manifest)
    return paths
```

### extract-edit-xml.py: Path-Based Extraction with Path Attribute
```python
# Source: Current codebase + _find_section_by_path pattern
from lib.xml_doc import _find_section_by_path

# In extract_edit_xml(), finding lookup changes:
section_path = f.get("section", "")  # now a slash-separated path
key = (xml_path, section_path)       # was: (xml_path, slug)

# Section lookup changes from flat findall to path-based:
section_el = _find_section_by_path(master_tree.getroot(), section_path)
if section_el is None:
    continue

# Edit section creation adds path attribute:
edit_section = etree.SubElement(
    root, "section",
    source=xml_path,
    slug=section_el.get("slug"),     # leaf slug for display
    path=section_path,               # full path for merge-back
    audience=info["audience"],
    document=info["document"],
)
```

### merge-edit-xml.py: Path-Based Merge
```python
# Source: Current codebase + _find_section_by_path pattern
from lib.xml_doc import _find_section_by_path

# Read path attribute (primary key) with slug fallback:
path = section_el.get("path") or section_el.get("slug", "")

# Replace flat findall with path-based lookup:
master_section = _find_section_by_path(master_tree.getroot(), path)
if master_section is None:
    errors.append(f"Section '{path}' not found in {source}")
    continue

# Mutation helpers already accept paths:
update_section_body(master_tree, path, edit_body)
update_section_refs(master_tree, path, edit_refs)
```

### sync-edits-to-xml.py: Heading-Level Reconstruction
```python
# Source: Design from CONTEXT.md decisions
HEADING_RE = re.compile(r"^(#{2,6})\s+", re.MULTILINE)

def _infer_paths(md_sections):
    """Infer slash-separated paths from (slug, body) tuples using heading levels.

    Returns list of (path, slug, body) tuples.
    """
    stack = []  # [(depth, slug)] -- tracks ancestor chain
    result = []

    for slug, body in md_sections:
        depth = _heading_depth(body)

        # Pop stack to find parent: any heading same-or-shallower pops
        while stack and stack[-1][0] >= depth:
            stack.pop()

        # Build path from remaining stack + current slug
        path = "/".join(s for _, s in stack) + ("/" if stack else "") + slug

        result.append((path, slug, body))
        stack.append((depth, slug))

    return result


def _heading_depth(body):
    """Extract heading depth from body (## = 2, ### = 3, etc.)."""
    m = HEADING_RE.search(body)
    if m:
        return len(m.group(1))
    return 2  # default to top-level if no heading found
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `doc["sections"]` flat loop | `walk_sections(doc["sections"])` | Phase 18 (xml_doc.py) | All section iteration becomes depth-aware |
| `findall("section")` flat lookup | `_find_section_by_path(root, path)` | Phase 18 (xml_doc.py) | Locates sections at any depth |
| `section["slug"]` as identifier | Slash-separated path from `walk_sections()` | Phase 18 (walk_sections) | Unique identifier at any depth |
| `update_section_body(tree, slug, ...)` | `update_section_body(tree, path, ...)` | Phase 18 (_find_section) | Already path-aware, no change needed |

**Deprecated/outdated:**
- `get_section_slugs()`: Backward-compat alias for top-level only. New code should use `get_section_paths()`.
- Flat `findall("section")` + slug match: Replaced by `_find_section_by_path()`.

## Script-by-Script Change Analysis

### verify-xml-refs.py (RPS-01, RPS-02)
**Current:** `verify_xml_file()` iterates `doc["sections"]` flat, uses `slug` in findings.
**Change:** Use `walk_sections()` to iterate all depths. Use `path` instead of `slug` in `_make_finding()`. The `group_id` changes from `f"{document}/{slug}"` to `f"{document}/{path}"`.
**Complexity:** LOW -- straightforward loop replacement + finding field change.
**Risk:** group_id format change must be compatible with downstream grouping.

### prepare-prose-verify.py (RPS-03)
**Current:** Iterates `doc["sections"]` flat, writes `{output_dir}/{slug}.json`.
**Change:** Use `walk_sections()`. Write to nested directories: `{output_dir}/{parent_path}/{slug}.json`. Manifest lists paths not slugs. Section JSON includes `path` field.
**Complexity:** MEDIUM -- directory structure change + manifest format change.
**Risk:** Downstream prose verification consumers must find files in new locations.

### extract-edit-xml.py (RPS-04)
**Current:** Groups findings by `(xml_path, slug)`. Finds sections via flat `findall("section")`. Edit section has `slug` attribute.
**Change:** Group by `(xml_path, path)`. Find sections via `_find_section_by_path()`. Add `path` attribute to edit section. Retain `slug` for display.
**Complexity:** MEDIUM -- lookup mechanism change + attribute addition.
**Risk:** Must preserve round-trip fidelity with merge-edit-xml.py.

### merge-edit-xml.py (RPS-05)
**Current:** Reads `slug` attribute, finds section via flat `findall("section")`. Calls `update_section_body(tree, slug, ...)`.
**Change:** Read `path` attribute (fall back to `slug` for backward compat). Find section via `_find_section_by_path()`. Mutation helpers already accept paths.
**Complexity:** LOW -- path attribute read + lookup mechanism swap. Mutation helpers need no change.
**Risk:** Backward compatibility if old edit XML without `path` attribute is encountered.

### sync-edits-to-xml.py (RPS-06)
**Current:** Flat marker split gives `(slug, body)` tuples. Matches by slug against `doc["sections"]` flat.
**Change:** After flat split, reconstruct tree from heading levels. Build slash-separated paths. Match by path against recursive tree. Use `update_section_body(tree, path, body)`.
**Complexity:** HIGH -- heading-level inference is new logic not covered by existing primitives.
**Risk:** Malformed heading hierarchies. Must handle skipped levels gracefully.

### load-audit-findings.py (RPS-01)
**Current:** Deduplicates by `(document, section, check, description)` where `section` is a slug.
**Change:** No structural change. `section` field now contains a slash-separated path. Deduplication still works because the key tuple uses the raw field value.
**Complexity:** MINIMAL -- the script is path-format-agnostic already.
**Risk:** None. The dedup key naturally handles paths.

## Open Questions

1. **Manifest backward compatibility for prepare-prose-verify.py**
   - What we know: Manifest changes from slug list to path list. Downstream consumers read the manifest.
   - What's unclear: Whether any external consumer depends on the current manifest format.
   - Recommendation: Change the manifest, add `"path"` field to section JSON alongside `"slug"`. This is a clean cutover like Phase 19's write-section.py change.

2. **sync-edits-to-xml.py heading fallback behavior**
   - What we know: Heading level determines depth. CONTEXT.md says headings are authoritative.
   - What's unclear: What if a section has no heading (body is just prose)?
   - Recommendation: Default to depth 0 (top-level) if no heading found. Log a warning.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | pyproject.toml |
| Quick run command | `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header` |
| Full suite command | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RPS-01 | Finding section field uses slash-separated paths | unit | `python3 -m pytest auto-doc/scripts/tests/test_verify_xml_refs.py -x` | Needs update |
| RPS-02 | Recursive ref verification audits each section independently | unit | `python3 -m pytest auto-doc/scripts/tests/test_verify_xml_refs.py -x` | Needs update |
| RPS-03 | Prose verify output in nested directories for all tree sections | unit | `python3 -m pytest auto-doc/scripts/tests/test_prepare_prose_verify.py -x` | Needs update |
| RPS-04 | Extract produces edit-group XML with path attribute at any depth | unit | `python3 -m pytest auto-doc/scripts/tests/test_extract_edit_xml.py -x` | Needs update |
| RPS-05 | Merge uses path attribute to locate correct tree position | unit | `python3 -m pytest auto-doc/scripts/tests/test_merge_edit_xml.py -x` | Needs update |
| RPS-06 | Sync reconstructs section tree from heading levels | unit | `python3 -m pytest auto-doc/scripts/tests/test_sync_edits.py -x` | Needs update |

### Sampling Rate
- **Per task commit:** `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header`
- **Per wave merge:** `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- None -- existing test infrastructure covers all phase requirements. Tests need updating (not creating) to use nested fixtures.

### Shared Test Fixtures
The existing test files each create their own XML fixtures. For Phase 20, nested XML fixtures should be added to each test file. A shared helper pattern already exists in test_xml_doc.py (`NESTED_SECTIONS_2`, `NESTED_SECTIONS_3`) that can be replicated. Build helpers (`_build_xml`, `_build_xml_with_refs`, `_build_master`) in each test file need extending to accept nested section structures via the `children` key.

## Sources

### Primary (HIGH confidence)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/lib/xml_doc.py` -- `walk_sections`, `_find_section_by_path`, `_find_section`, mutation helpers (Phase 18)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/verify-xml-refs.py` -- current flat iteration pattern
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/prepare-prose-verify.py` -- current flat output pattern
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/extract-edit-xml.py` -- current flat lookup pattern
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/merge-edit-xml.py` -- current flat merge pattern
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/sync-edits-to-xml.py` -- current flat sync pattern
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/load-audit-findings.py` -- current dedup pattern
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/assemble-markdown.py` -- Phase 19 walk_sections adoption (reference implementation)
- All 6 test files for the above scripts -- verified 85 tests passing

### Secondary (MEDIUM confidence)
- `.planning/phases/20-recursive-pipeline-script-updates/20-CONTEXT.md` -- locked design decisions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all primitives exist in xml_doc.py, verified by reading source
- Architecture: HIGH -- patterns directly observed in Phase 19's assemble-markdown.py and write-section.py
- Pitfalls: HIGH -- derived from reading actual script code and understanding the flat-to-recursive transition
- Sync heading reconstruction: MEDIUM -- new logic not covered by existing primitives, design from CONTEXT.md

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (stable internal codebase, no external dependencies changing)
