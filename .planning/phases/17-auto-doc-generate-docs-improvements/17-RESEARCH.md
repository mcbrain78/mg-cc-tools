# Phase 17: Auto-Doc Generate Docs Improvements - Research

**Researched:** 2026-03-23
**Domain:** LLM agent prompt engineering, JSON filtering/splitting, Claude Code subagent efficiency
**Confidence:** HIGH

## Summary

Phase 17 improves the auto-doc generate pipeline efficiency via two complementary changes: (1) adding Serena-based source code exploration guidance to all 5 writer agent .md files, and (2) creating a `split-scan-by-audience.py` script that produces per-audience view files from docs-scan.json so each writer reads a small focused file instead of the full 19k-token scan. The orchestrator (`auto-doc-generate.md`) is updated to call the split script and route view file paths to writers.

This is a well-scoped phase with clear boundaries: 5 writer agent .md edits (adding Serena guidance), 1 new Python script with tests, and targeted orchestrator prompt changes. No schema changes, no scan pipeline changes, no new commands. The existing codebase provides strong precedents for all three work items.

**Primary recommendation:** Implement the split-scan script first (it is independently testable), then update the orchestrator to call it and route view paths, and finally add Serena guidance to writer agents. This ordering ensures each change can be validated before building on it.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Add "Source Code Exploration" principle to all 5 writer agent .md files: `glossary-writer.md`, `end-user-writer.md`, `developer-writer.md`, `agent-writer.md`, `devops-writer.md`
- Writers use `get_symbols_overview` (depth: 1) to understand file structure before reading
- Writers use `find_symbol` with `include_body: true` for specific functions/classes they need to document
- Writers use `find_symbol` with `include_info: true` for signatures and docstrings only
- Writers use `Read` only for files Serena cannot parse (yaml, toml, config, markdown, shell scripts, SQL, Dockerfile, .env.example)
- Writers must never read an entire source file -- explore structure first, then read specific symbols
- Pattern is adapted from scan-audience.md but oriented for writers who need more code context (include_body: true is the right default)
- Glossary writer gets the same Serena guidance as audience writers
- New script: `split-scan-by-audience.py` with two modes (audience mode and glossary mode)
- Audience mode (`--mode audience --audience {name} --documents ARCHITECTURE,DEVELOPER_GUIDE`): extracts `project_model` + `gsd_context` + filtered `source_material_index` + filtered `gap_analysis`
- Glossary mode (`--mode glossary`): extracts `project_model` + `gsd_context` + all `source_material_index` keys with `source_files` reduced to filenames only
- Output files: `{TMP_DIR}/scan-view-{audience}.json` for audience mode, `{TMP_DIR}/scan-view-glossary.json` for glossary mode
- View files use same top-level key structure as docs-scan.json so writer agents' existing access patterns work unchanged
- Keys not relevant to the view (`staleness_report`, `note_classifications`, `scan_date`) are omitted
- Per-audience invocations (one call per audience + one for glossary), not batch mode
- Orchestrator calls split-scan-by-audience.py once per audience + once for glossary before spawning writer agents
- Orchestrator passes the view file path as `scan_data_path` in each writer agent's prompt
- No changes needed in writer agent .md files for scan view routing
- In update mode, all audience views are created eagerly
- Audience-to-document mapping comes from `.docs.config.json`

### Claude's Discretion
- Internal structure of `split-scan-by-audience.py` (argument parsing, filtering implementation, error handling)
- Test structure and organization for the new script
- Exact wording of Serena guidance in each writer agent (adapt to audience-specific writing patterns)
- Whether to add any logging/metrics to track token reduction

### Deferred Ideas (OUT OF SCOPE)
- Single-write manifests -- explicitly deferred; per-entry pattern retained for reliability
- Wall time estimate precision -- rough directional estimates only, not commitments
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GEN-07 | All five writer agents use Serena-based source code exploration | Scan-audience.md lines 67-74 and 161 provide the working Serena pattern to adapt; all 5 writer agents examined and insertion points identified |
| GEN-08 | Split-scan script produces per-audience view files | split-findings.py precedent for JSON filtering; lib/json_io.py for atomic I/O; .docs.config.json defines audience-to-document mapping |
| GEN-09 | Glossary-specific view with all keys but filenames-only source_files | Glossary mode is a variant of audience mode; same script, different filtering logic |
| GEN-10 | Orchestrator splits scan before spawning writers and passes view file paths | auto-doc-generate.md orchestrator structure analyzed; scan_data_path routing already exists in Stage 1/2 prompts |
| GEN-11 | View files preserve same top-level key structure as docs-scan.json | Schema analyzed; view includes project_model, gsd_context, source_material_index, gap_analysis; omits staleness_report, note_classifications, scan_date |
| GEN-12 | Each audience view fits in a single read operation | Current 19k tokens split into ~5k per audience view; well under 10k Read limit |
| GEN-13 | Existing per-entry manifest write pattern retained unchanged | No changes needed; manifest emission in writer agents and orchestrator merge logic untouched |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (json, argparse, os, sys, pathlib) | 3.11+ | Script implementation | Project convention: zero external dependencies for pipeline scripts |
| lib/json_io.py | internal | Atomic JSON load/save | Shared module used by all auto-doc scripts; provides load_json and save_json |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | latest | Test framework | Tests for split-scan-by-audience.py |
| subprocess (in tests) | stdlib | CLI invocation testing | Project test pattern: invoke scripts as CLI tools, no direct imports of kebab-case modules |
| tempfile (in tests) | stdlib | Temp directories for test isolation | All auto-doc tests use tempfile.TemporaryDirectory |

### Alternatives Considered
None. All decisions are locked. This phase uses the same stack as every other auto-doc script.

**Installation:**
```bash
# No new dependencies needed -- stdlib only for scripts, pytest already in dev extras
```

## Architecture Patterns

### Recommended Project Structure
```
auto-doc/
  scripts/
    split-scan-by-audience.py    # NEW: per-audience view splitter
    lib/json_io.py               # EXISTING: shared atomic JSON I/O
    tests/
      test_split_scan_by_audience.py  # NEW: tests for the splitter
  agents/
    glossary-writer.md           # MODIFIED: add Serena guidance
    end-user-writer.md           # MODIFIED: add Serena guidance
    developer-writer.md          # MODIFIED: add Serena guidance
    agent-writer.md              # MODIFIED: add Serena guidance
    devops-writer.md             # MODIFIED: add Serena guidance
  commands/
    auto-doc-generate.md         # MODIFIED: add split-scan calls, route view paths
```

### Pattern 1: JSON Filtering Script (split-scan-by-audience.py)

**What:** A CLI script that reads docs-scan.json, filters to a subset relevant to a specific audience (or glossary), and writes a view file with the same top-level key structure.

**When to use:** Before spawning writer agents, to reduce each agent's input from 19k tokens to ~5k tokens.

**Precedent:** `codebase-health/scripts/split-findings.py` -- same concept of reading a shared JSON contract and producing filtered subsets. Key differences: split-findings produces two output types (markdown + JSON), while split-scan produces uniform JSON views.

**CLI interface:**
```bash
# Audience mode
python3 {SCRIPTS_DIR}/split-scan-by-audience.py \
    --input .mg/docs/docs-scan.json \
    --output {TMP_DIR}/scan-view-developers.json \
    --mode audience \
    --audience developers \
    --documents ARCHITECTURE,DEVELOPER_GUIDE,QUICK_REFERENCE

# Glossary mode
python3 {SCRIPTS_DIR}/split-scan-by-audience.py \
    --input .mg/docs/docs-scan.json \
    --output {TMP_DIR}/scan-view-glossary.json \
    --mode glossary
```

**Filtering logic (audience mode):**
1. Load full docs-scan.json
2. Copy `project_model` and `gsd_context` verbatim
3. Filter `source_material_index`: for each key `{DOCUMENT}/{section-slug}`, include only if `DOCUMENT` is in the `--documents` list
4. Filter `gap_analysis`: include `undocumented_components` verbatim, filter `missing_for_audience` to only the target audience
5. Omit `staleness_report`, `note_classifications`, `scan_date`, `project`, `root_path`, `mode`, `last_generated`

**Filtering logic (glossary mode):**
1. Load full docs-scan.json
2. Copy `project_model` and `gsd_context` verbatim
3. Include ALL `source_material_index` keys (for term discovery), but reduce each entry's `source_files` array to filenames only (basename, not full path)
4. Include full `gap_analysis`
5. Omit `staleness_report`, `note_classifications`, `scan_date`, `project`, `root_path`, `mode`, `last_generated`

### Pattern 2: Serena Guidance in Writer Agents

**What:** Adding a "Source Code Exploration" principle section to each writer agent .md file that instructs the LLM to use Serena tools instead of blanket file reads.

**When to use:** In the Principles section of each writer agent, as the first principle (highest visibility).

**Source pattern (from scan-audience.md, adapted for writers):**

The scan-audience.md has two key locations:
1. **Process step** (lines 67-73): Inline guidance during the "explore file structure" step
2. **Principles section** (line 161): Summary principle "Symbols first, Read second"

For writers, the guidance goes in the Principles section because writers already have a well-defined Process section that reads source files from the `source_material_index`. The key difference from scan agents is:
- Scan agents use Serena to decide WHICH files are relevant (discovery)
- Writers already know which files are relevant (from the scan index); they use Serena to read those files MORE EFFICIENTLY (specific symbols instead of whole files)

**Adaptation per audience:**
- **Developer writer**: Emphasize `include_body: true` for code examples and type signatures
- **Agent writer**: Emphasize `include_body: true` for precise function/class documentation
- **End-user writer**: Emphasize `include_info: true` for signatures (users need behavior, not implementation); `include_body: true` sparingly for understanding user-facing logic
- **DevOps writer**: Emphasize `include_info: true` for deployment/config-related symbols; `include_body: true` for configuration parsing
- **Glossary writer**: Emphasize `include_body: true` for accurate term definitions (need to understand what components actually do)

### Pattern 3: Orchestrator View File Routing

**What:** The generate orchestrator calls split-scan-by-audience.py before spawning writers, then passes the view file path as `scan_data_path` instead of the full docs-scan.json path.

**Integration point in auto-doc-generate.md:**

Currently, all writer agents receive:
```
Scan data path: {project_root}/.mg/docs/docs-scan.json
```

After this phase, the orchestrator will:
1. In Step 3 (Prepare Workspace), add view splitting calls after directory creation
2. In Stage 1 (glossary), pass `scan-view-glossary.json` path
3. In Stage 2 (audience writers), pass `scan-view-{audience}.json` path
4. In Stage 3 (glossary reconciliation), pass `scan-view-glossary.json` path again

The orchestrator still reads the full docs-scan.json itself (for staleness report, note classifications, mode detection) -- only subagents get view files.

### Anti-Patterns to Avoid
- **Modifying writer agents to understand view routing.** The orchestrator controls `scan_data_path` -- writers just read whatever path they receive. No conditionals in writer agents.
- **Batch mode for split-scan.** Per-invocation is simpler, matches the existing per-audience CLI pattern, and keeps each call independently testable.
- **Including staleness_report or note_classifications in view files.** These are orchestrator concerns, not writer concerns. Writers never read these fields.
- **Changing the view file key structure.** View files must use the same keys as docs-scan.json so writer agents work without changes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic JSON write | Custom temp-file logic | `lib/json_io.py` `save_json()` | Already handles temp file + os.replace + directory creation |
| JSON loading with defaults | Manual file-exists checks | `lib/json_io.py` `load_json(path, default={})` | Consistent error handling across all scripts |
| Source_material_index key parsing | Custom string splitting | Simple `key.split("/", 1)` | The key format is `{DOCUMENT}/{section-slug}` -- splitting on first `/` is sufficient |

**Key insight:** All the infrastructure for this phase already exists. The new script follows well-established patterns from 14 existing auto-doc scripts.

## Common Pitfalls

### Pitfall 1: View File Key Filtering Must Match Document Names Exactly
**What goes wrong:** The `source_material_index` keys use uppercase document names (`ARCHITECTURE/system-overview`), while `.docs.config.json` uses the same uppercase format. A case mismatch in filtering would silently drop entries.
**Why it happens:** The `--documents` argument is a comma-separated list parsed from config. If the orchestrator passes lowercase or mixed case, filtering fails.
**How to avoid:** The orchestrator reads `audiences.{name}.documents` from config (which is already uppercase: `["ARCHITECTURE", "DEVELOPER_GUIDE"]`) and passes it directly. The script should compare document prefixes case-sensitively.
**Warning signs:** A view file with zero source_material_index entries when the full scan has entries for that audience.

### Pitfall 2: Glossary View Must Preserve Full Key Structure
**What goes wrong:** Glossary mode reduces `source_files` to filenames but must preserve the full `{DOCUMENT}/{section-slug}` key structure. Accidentally flattening or grouping by document would break the glossary writer's term discovery.
**Why it happens:** The purpose of the glossary view is term discovery from ALL documents, so the writer needs to see which sections exist across all audiences.
**How to avoid:** Copy `source_material_index` keys verbatim; only modify the `source_files` arrays within each entry (replace full paths with basenames).
**Warning signs:** Glossary writer failing to discover terms from specific documents.

### Pitfall 3: Orchestrator Must Still Read Full docs-scan.json
**What goes wrong:** If the orchestrator switches to reading a view file, it loses access to `staleness_report`, `note_classifications`, and other fields needed for the approval flow (Step 2).
**Why it happens:** The view files intentionally omit these fields.
**How to avoid:** The orchestrator continues to load `.mg/docs/docs-scan.json` in Step 1 for its own use. View files are created in Step 3 (after the approval flow) and passed only to subagents.
**Warning signs:** Update mode approval flow showing zero stale sections or zero notes.

### Pitfall 4: install.sh Already Handles New Scripts Automatically
**What goes wrong:** Nothing -- but a common fear is that install.sh needs updating for the new script.
**Why it happens:** `install.sh` uses a wildcard copy: `for py_file in "${SCRIPT_DIR}"/scripts/*.py`.
**How to avoid:** No action needed. The new `split-scan-by-audience.py` will be automatically deployed by the existing install.sh wildcard.
**Warning signs:** N/A -- this is a non-issue, documented to prevent unnecessary install.sh changes.

### Pitfall 5: sed Resolution for {SCRIPTS_DIR} in Orchestrator
**What goes wrong:** If the orchestrator references `{SCRIPTS_DIR}/split-scan-by-audience.py`, the `{SCRIPTS_DIR}` placeholder must be resolved by install.sh at install time.
**Why it happens:** auto-doc-generate.md already uses `{SCRIPTS_DIR}` extensively -- the placeholder is already resolved for all script references in command files.
**How to avoid:** Use the same `{SCRIPTS_DIR}/split-scan-by-audience.py` pattern. The existing sed loop in install.sh handles it.
**Warning signs:** N/A -- existing pattern, already works.

### Pitfall 6: gap_analysis Filtering for Audience Mode
**What goes wrong:** The `gap_analysis.missing_for_audience` dict contains entries for all audiences. If not filtered, each writer sees gaps for other audiences and may try to address them.
**Why it happens:** The full docs-scan.json has gap analysis for all audiences combined.
**How to avoid:** In audience mode, filter `missing_for_audience` to only include the target audience key. Preserve `undocumented_components` (these are audience-agnostic).
**Warning signs:** Writer agents reporting or attempting to address gaps from other audiences.

## Code Examples

Verified patterns from the existing codebase:

### Atomic JSON Load/Save (from lib/json_io.py)
```python
# Source: auto-doc/scripts/lib/json_io.py
from lib.json_io import load_json, save_json

# Load with default
data = load_json(scan_path, default={})

# Save atomically (temp file + os.replace)
save_json(output_path, view_data)
```

### CLI Pattern (from write-scan-output.py)
```python
# Source: auto-doc/scripts/write-scan-output.py
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--input", required=True, dest="input_file", help="...")
    parser.add_argument("--output", required=True, help="...")
    parser.add_argument("--mode", required=True, choices=["audience", "glossary"], help="...")
    parser.add_argument("--audience", help="...")
    parser.add_argument("--documents", help="...")
    args = parser.parse_args()
    # ... implementation
```

### Test Pattern (from test_add_manifest_entry.py)
```python
# Source: auto-doc/scripts/tests/test_add_manifest_entry.py
import json
import os
import subprocess
import sys
import tempfile

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "split-scan-by-audience.py",
)

class TestSplitScanAudienceMode:
    def test_filters_source_material_to_matching_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "view.json")
            # Write full scan data, invoke script, verify filtered output
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--mode", "audience",
                 "--audience", "developers",
                 "--documents", "ARCHITECTURE,DEVELOPER_GUIDE"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
```

### Source Material Index Key Filtering
```python
# Filter source_material_index by document name prefix
def filter_source_material(index, document_list):
    """Keep only entries whose document prefix is in document_list."""
    filtered = {}
    for key, value in index.items():
        doc_prefix = key.split("/", 1)[0]
        if doc_prefix in document_list:
            filtered[key] = value
    return filtered
```

### Glossary Source Files Reduction
```python
# Reduce source_files to filenames only for glossary view
import os

def reduce_source_files_to_filenames(index):
    """Replace full paths with basenames in source_files arrays."""
    reduced = {}
    for key, value in index.items():
        entry = dict(value)  # shallow copy
        if "source_files" in entry:
            entry["source_files"] = [
                os.path.basename(f) for f in entry["source_files"]
            ]
        reduced[key] = entry
    return reduced
```

### Serena Guidance for Writer Agents (adapted from scan-audience.md)
```markdown
## Principles (addition to each writer agent)

- **Symbols first, Read second.** When reading source files from the scan index,
  always call `get_symbols_overview` (depth: 1) first to understand the file
  structure. Use `find_symbol` with `include_body: true` for functions and classes
  you need to document in detail. Use `find_symbol` with `include_info: true` for
  signatures and docstrings only. Only fall back to `Read` for files Serena cannot
  parse (yaml, toml, config, markdown, shell scripts, SQL, Dockerfile, .env.example).
  Never read an entire source file blind.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Writers read full files via `Read(file.py)` | Writers use Serena symbols-first | Phase 17 | Estimated ~30% token reduction for agents bottleneck |
| All agents read full 19k docs-scan.json | Per-audience ~5k view files | Phase 17 | Eliminates ~30 chunked reads per generate run |
| Scan agents have Serena guidance | All agents have Serena guidance | Phase 17 (builds on Phase 3) | Consistency across scan and generate pipelines |

**Deprecated/outdated:**
- Nothing deprecated. This phase adds new efficiency patterns without removing existing functionality.

## Open Questions

1. **Exact token savings**
   - What we know: Road-runner generate used ~630k tokens. Agents writer was 175.3k (bottleneck).
   - What's unclear: Exact reduction from Serena guidance varies by project size and code complexity.
   - Recommendation: Treat estimates as directional. Verify with a road-runner generate run after changes.

2. **gap_analysis.undocumented_components filtering**
   - What we know: `undocumented_components` is a flat list of component paths with no audience tagging.
   - What's unclear: Whether writers use undocumented_components from the view (they likely don't -- gap analysis is mainly for scan reporting).
   - Recommendation: Include `undocumented_components` verbatim in audience views (cheap, safe) and filter `missing_for_audience` to target audience only.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `python3 -m pytest`) |
| Config file | pyproject.toml (project-level) |
| Quick run command | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py --tb=short -q --no-header` |
| Full suite command | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GEN-07 | Writer agents use Serena guidance | manual-only | N/A -- .md file changes, verified by reading agent files | N/A |
| GEN-08 | Split-scan audience mode filters source_material_index by document list | unit | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py -k audience --tb=short -q --no-header` | Wave 0 |
| GEN-09 | Split-scan glossary mode reduces source_files to filenames | unit | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py -k glossary --tb=short -q --no-header` | Wave 0 |
| GEN-10 | Orchestrator routes view paths to writers | manual-only | N/A -- .md orchestrator changes, verified by reading command file | N/A |
| GEN-11 | View files preserve top-level key structure | unit | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py -k structure --tb=short -q --no-header` | Wave 0 |
| GEN-12 | Each audience view fits single read | unit | `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py -k size --tb=short -q --no-header` | Wave 0 |
| GEN-13 | Per-entry manifest pattern unchanged | existing | `python3 -m pytest auto-doc/scripts/tests/test_add_manifest_entry.py --tb=short -q --no-header` | Existing |

### Sampling Rate
- **Per task commit:** `python3 -m pytest auto-doc/scripts/tests/test_split_scan_by_audience.py --tb=short -q --no-header`
- **Per wave merge:** `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `auto-doc/scripts/tests/test_split_scan_by_audience.py` -- covers GEN-08, GEN-09, GEN-11, GEN-12
- No framework install needed -- pytest already configured
- No conftest needed -- existing test pattern uses standalone tempfile.TemporaryDirectory

## Sources

### Primary (HIGH confidence)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/agents/scan-audience.md` -- Serena guidance pattern (lines 67-74, 161)
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/commands/auto-doc-generate.md` -- Orchestrator structure, scan_data_path routing
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/agents/*.md` -- All 5 writer agent files examined for insertion points
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/lib/json_io.py` -- Shared I/O module
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/references/.docs.config.json` -- Audience-to-document mapping
- `/home/mcbrain/mg_projects/mg-cc-tools/codebase-health/scripts/split-findings.py` -- JSON filtering script precedent
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/install.sh` -- Deployment/sed resolution patterns
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/scripts/tests/test_add_manifest_entry.py` -- Test pattern precedent
- `/home/mcbrain/mg_projects/mg-cc-tools/auto-doc/references/schema.md` -- docs-scan.json structure
- `/home/mcbrain/mg_projects/mg-cc-tools/docs/work-queue/todo/auto-doc-v1.2/concept.md` -- Problem statement and evidence

### Secondary (MEDIUM confidence)
- None needed -- all information sourced directly from the codebase

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- identical to existing auto-doc scripts, no new dependencies
- Architecture: HIGH -- all patterns directly observable in existing code, all integration points examined
- Pitfalls: HIGH -- derived from analyzing actual code structure and data flow
- Test approach: HIGH -- follows established 118-test suite patterns exactly

**Research date:** 2026-03-23
**Valid until:** indefinite (internal codebase patterns, not external library versions)
