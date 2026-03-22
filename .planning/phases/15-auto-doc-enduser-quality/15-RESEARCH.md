# Phase 15: Auto Doc End-User Quality - Research

**Researched:** 2026-03-22
**Domain:** LLM-agent documentation generation -- template redesign, interface-aware writing, synthesized sections
**Confidence:** HIGH

## Summary

This phase transforms the end-user documentation pipeline from generic CLI-centric output to functional, interface-aware documentation. The work spans 5 files that need significant edits (USER_GUIDE template, scan-audience agent, end-user-writer agent, auto-doc-scan command, schema) plus 1 file deletion (DOMAIN_SPECIFIC template), with no Python script changes required.

The changes fall into three independent concern areas: (1) interface detection in the scan pipeline with config persistence, (2) template restructuring with new section types (SYNTHESIZED, BOUNDARY) and replacement exemplars, and (3) writer agent updates for interface-aware generation and synthesized section handling. The areas can be implemented sequentially within a phase, but the template must be updated before the scan agent and writer agent since both consume template comments.

**Primary recommendation:** Start with schema and template changes (the data contract), then scan-side changes (interface detection + SYNTHESIZED/BOUNDARY parsing), then writer-side changes (interface-aware generation + synthesized section handling), and finally the deletion of DOMAIN_SPECIFIC.template.md. This order ensures downstream consumers always have the contracts they need.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Interface detection in scan: config field `user_interfaces` checked first (no detection needed), then heuristic detection + user confirmation via `AskUserQuestion`
- Confirmation chain: confirmed -> persist to config; corrected -> persist corrected; absent/non-interactive -> fall back to no user_interfaces, writer uses CLI-style
- Writer consumes user_interfaces: new step between "Read context" and "For each document" reads primary interface, procedures default to that style
- type mappings: web -> click paths, CLI -> commands, API -> requests/responses; secondary as callout tips
- Per-audience exclusion rules for end-users in scan-audience.md (specific exclusion and inclusion lists defined)
- Refined PURPOSE comments in USER_GUIDE template (Getting Started reframed as first use of running system)
- Template restructuring: 7-section structure (Overview, Key Concepts, Workflows, Getting Started, Common Tasks, Configuration, Troubleshooting)
- No update-mode migration: old end-user docs deleted, fresh generation with new template
- SYNTHESIZED comment pattern: `<!-- SYNTHESIZED: field1, field2 -->`, scan writes index entry with `source_files: []` and `synthesized_from: [field list]`, no validation at scan time
- BOUNDARY comment pattern: `<!-- BOUNDARY: ... -->`, negative guidance for scan (don't index) and writer (don't generate, cross-reference)
- Synthesized section quality control: generate purely from structured fields, emit TODO placeholder when insufficient data
- New section exemplars: Overview, Key Concepts, Workflows -- all use road-runner portfolio analytics domain, web-UI style
- Replacement exemplars for existing sections: all replaced with functional-first, interface-aware versions showing web-UI reference case
- Writer functional-first pattern: goal -> system behavior -> steps through primary interface -> secondary tip -> expected results
- Cross-audience boundary enforcement rules (installation -> devops, API details -> developer, etc.)
- Projects where end-users ARE developers: not a configuration problem, just don't enable end-users audience
- Delete DOMAIN_SPECIFIC.template.md
- No Python script changes needed (write-scan-output.py, merge-scan.py, staleness-check.py all pass through correctly)
- `synthesized_from` added as optional string-array field on source_material_index entries in schema.md
- AskUserQuestion added to auto-doc-scan allowed-tools
- Interface detection is a sub-step within Step 1 (Orient), performed by the orchestrator

### Claude's Discretion
- Exact wording of BOUNDARY comments for each template section
- How to structure the scan agent's SYNTHESIZED parsing implementation
- Whether to add BOUNDARY comments to non-end-user templates as well
- How to handle edge cases where heuristic detection is ambiguous (multiple equally-likely interfaces)
- Internal organization of the end-user-writer.md agent rewrite
- Exact content of the 3 new synthesized section exemplars (within the constraints above)

### Deferred Ideas (OUT OF SCOPE)
- Multi-interface projects with more than 2 interfaces
- Synthesized sections for non-end-user audiences
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EUQ-01 | Scan phase detects primary user interface type and persists to config | Interface detection sub-step in Orient (Step 1), config persistence chain, AskUserQuestion for confirmation, heuristic patterns documented |
| EUQ-02 | Writer generates procedures through primary interface style | Writer agent gains new process step reading user_interfaces from scan data, type->style mapping (web/CLI/API), secondary interfaces as callout tips |
| EUQ-03 | End-user audience scan excludes infrastructure/internal files | Exclusion rules added to scan-audience.md for end-users audience, inclusion rules for user-facing content |
| EUQ-04 | USER_GUIDE template uses 7-section functional-first structure with consistent exemplars | Template restructure with 3 new synthesized sections + 4 rewritten sections, road-runner domain, web-UI exemplars |
| EUQ-05 | Old end-user docs deleted and regenerated fresh | No migration path -- generate command's initial mode behavior handles this by nature |
| EUQ-06 | Scan agent and writer support SYNTHESIZED sections | SYNTHESIZED comment parsing in scan-audience, synthesized_from field in schema, writer fallback for missing data |
| EUQ-07 | Scan agent and writer recognize BOUNDARY comments | BOUNDARY parsing in scan-audience (skip indexing), writer cross-references named alternate document |
| EUQ-08 | Writer follows functional-first pattern | Goal -> system behavior -> steps through interface -> secondary tip -> expected results pattern in writer conventions |
| EUQ-09 | Cross-audience boundaries enforced | BOUNDARY comments in template + writer enforcement: installation/infra -> devops, API -> developer, system config -> devops |
| EUQ-10 | DOMAIN_SPECIFIC template removed | Delete auto-doc/references/templates/end-users/DOMAIN_SPECIFIC.template.md |
</phase_requirements>

## Standard Stack

### Core

This phase modifies existing markdown files and the JSON schema. No new libraries or dependencies are introduced.

| File | Purpose | Change Type |
|------|---------|-------------|
| `auto-doc/references/schema.md` | Data contract | Add `user_interfaces` to project_model, add `synthesized_from` to source_material_index entries |
| `auto-doc/references/templates/end-users/USER_GUIDE.template.md` | End-user template | Complete rewrite: 7-section structure, new comment types, new exemplars |
| `auto-doc/agents/scan-audience.md` | Scan subagent | Add exclusion rules, SYNTHESIZED parsing, BOUNDARY parsing |
| `auto-doc/agents/end-user-writer.md` | Writer agent | Add interface-aware generation, synthesized section handling, BOUNDARY handling, functional-first pattern |
| `auto-doc/commands/auto-doc-scan.md` | Scan orchestrator | Add AskUserQuestion to allowed-tools, add interface detection sub-step in Orient |
| `auto-doc/references/.docs.config.json` | Default config | Add `user_interfaces` field (optional, empty by default) |

### Files to Delete

| File | Reason |
|------|--------|
| `auto-doc/references/templates/end-users/DOMAIN_SPECIFIC.template.md` | Removed from v1.1 scope per locked decision |

### No Changes Required

| File | Reason |
|------|--------|
| `auto-doc/scripts/write-scan-output.py` | Validates key format only, not entry contents -- `synthesized_from` passes through |
| `auto-doc/scripts/merge-scan.py` | Passes through `project_model` unchanged, including new `user_interfaces` field |
| `auto-doc/scripts/staleness-check.py` | Returns `None` for empty sources (line 149-150) -- synthesized sections with `sources: []` treated as fresh |
| `auto-doc/scripts/add-manifest-entry.py` | Validates document/section + non-empty symbols/file_paths -- synthesized sections may have no references and thus skip manifest emission per existing writer logic |
| `auto-doc/commands/auto-doc-generate.md` | No changes needed -- already passes `scan_data_path` to writer, writer already reads full scan data |
| `auto-doc/install.sh` | Template copying uses `cp -r` which handles subdirectory changes automatically; no new sed placeholders needed |

## Architecture Patterns

### Pattern 1: Template Comment Hierarchy

The USER_GUIDE template uses a layered comment system. Each section heading has one or more HTML comments that guide both the scan agent and writer agent.

**Current pattern (unchanged):**
```
<!-- PURPOSE: ... --> -- What the section covers
<!-- EXAMPLE: ... --> -- What good output looks like
<!-- OPTIONAL -- delete if not applicable --> -- Section can be skipped
```

**New patterns (Phase 15):**
```
<!-- SYNTHESIZED: field1, field2 --> -- Section generated from project model fields, not source files
<!-- BOUNDARY: {description of what belongs elsewhere} --> -- Negative guidance: do not index or generate this content
```

**Parsing rules for scan agent:**
1. If section has `<!-- SYNTHESIZED: ... -->`: split value on commas, trim whitespace to get field list. Write index entry with `"source_files": []` and `"synthesized_from": [field list]`. Skip Glob/Grep source file search.
2. If section has `<!-- BOUNDARY: ... -->`: record boundary text. Do NOT search for files matching the bounded content. Boundary guides what NOT to include.
3. If section has `<!-- PURPOSE: ... -->` (existing behavior): search for matching source files per existing logic.
4. A section can have both SYNTHESIZED and BOUNDARY (though this combination would be unusual).

**Writer rules:**
1. If `synthesized_from` is present and `source_files` is empty: generate from named project model fields, not from source files.
2. If project model lacks sufficient data for a synthesized section: emit `<!-- TODO: needs manual input -- insufficient scan data for this section -->` placeholder.
3. If a `<!-- BOUNDARY: ... -->` exists for a section: do not generate bounded content, instead add a cross-reference callout to the named alternate document.

### Pattern 2: Interface Detection Flow

The interface detection logic runs within Step 1 (Orient) of the scan command, as the last analysis step before writing `scan-project.json`.

```
Priority chain:
  1. Config has user_interfaces field? -> Use as-is, no detection
  2. Heuristic detection -> Present to user via AskUserQuestion -> User confirms/corrects
  3. Non-interactive / user absent -> Omit user_interfaces (field absent), writer falls back to CLI

Persistence:
  User confirms -> write to scan-project.json AND persist to .mg/docs/.docs.config.json
  User corrects -> use corrected values, persist both
  Fallback -> user_interfaces absent from scan-project.json (no config change)
```

**Heuristic detection principles:**
- Front-end frameworks with routes/templates -> `web`
- CLI frameworks (argument parsers, command groups) -> `cli`
- API-only frameworks without UI layer -> `api`
- Orchestration platforms with dashboards -> `web`
- Disambiguate with directory structure: `templates/`, `static/`, `pages/`, `app/` -> web UI

### Pattern 3: Writer Interface-Aware Step

New step in writer Process between "Read context" and "For each document":

```
1. Read context (existing)
2. NEW: Read project_model.user_interfaces from scan data
   - Identify primary interface (object with primary: true)
   - If no user_interfaces: default to CLI style (backward compatible)
   - Set interface_style for all procedures
3. For each document... (existing, now interface-aware)
```

Per-section behavior based on interface type:
- `type: "web"` -> describe click paths, form fields, screen states, expected visual results
- `type: "cli"` -> describe commands, flags, expected terminal output
- `type: "api"` -> describe requests, responses, status codes
- Secondary interfaces -> `> **Power user tip:** ...` callouts

### Pattern 4: Functional-First Section Structure

Every section in the end-user guide follows this structure:

```
1. Goal: What is the user accomplishing? Why?
2. System behavior: What will happen? How long? What to expect?
3. Steps through primary interface (web/CLI/API)
4. Secondary interface tip (if applicable)
5. Expected results: What does the user see when done?
```

### Anti-Patterns to Avoid

- **Don't make synthesized sections source-dependent.** The whole point of SYNTHESIZED is that content comes from project model fields, not source files. If a synthesized section reads source files, it defeats the purpose and creates incorrect staleness tracking.
- **Don't treat BOUNDARY as OPTIONAL.** BOUNDARY means "this content belongs elsewhere" -- the section still exists, it just cross-references instead of inlining. OPTIONAL means "skip if not applicable."
- **Don't hardcode interface style per section.** The interface style comes from `user_interfaces` at runtime, not from the template. Templates show web-UI exemplars as reference, but the actual generation adapts to detected interface.
- **Don't duplicate installation in Getting Started.** The BOUNDARY comment on Getting Started explicitly redirects installation to devops OPERATIONS.md. Getting Started covers first use of a running system.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Interface detection | Custom detection framework | Simple heuristic scan within Orient step | Detection is a one-time sub-step, not a reusable engine. Config persistence handles subsequent runs. |
| Synthesized section generation | Source file reading fallback | Pure project model field consumption | CONTEXT.md explicitly requires synthesized sections to NOT read source files -- prevents hallucination |
| Config persistence | Manual JSON editing instructions | Atomic read-modify-write in Orient step | Already have json_io.py pattern from other scripts, reuse same approach |

## Common Pitfalls

### Pitfall 1: SYNTHESIZED Entries Must Always Be Produced
**What goes wrong:** Scan agent skips creating source_material_index entries for SYNTHESIZED sections because there are no source files.
**Why it happens:** The agent's existing logic only creates entries when it finds source files.
**How to avoid:** SYNTHESIZED parsing rule must explicitly create an entry with `"source_files": []` and `"synthesized_from": [field list]` even when no files are found. The entry's presence triggers the writer's synthesis path.
**Warning signs:** Writer skips synthesized sections or treats them as OPTIONAL.

### Pitfall 2: write-scan-output.py Key Validation
**What goes wrong:** Scan entries for synthesized sections might fail key format validation.
**Why it happens:** `write-scan-output.py` validates key format with regex `^[A-Z][A-Z0-9_]+/[a-z0-9]+(?:-[a-z0-9]+)*$`. Synthesized sections still use standard `DOCUMENT/section-slug` keys.
**How to avoid:** Ensure section slugs for new sections (overview, key-concepts, workflows) follow the existing hyphenated-lowercase format. The regex already accepts these.
**Warning signs:** write-scan-output.py rejects scan output for end-users audience.

### Pitfall 3: AskUserQuestion in Non-Interactive Environments
**What goes wrong:** Interface detection blocks the scan pipeline when running non-interactively.
**Why it happens:** AskUserQuestion is added to scan allowed-tools, but some environments may not have a human present.
**How to avoid:** The confirmation chain has an explicit fallback: if user is absent or non-interactive, omit `user_interfaces` field entirely. Writer falls back to CLI-style docs. Scan must NOT block on this.
**Warning signs:** Scan hangs waiting for user input when run as part of an automated workflow.

### Pitfall 4: Template Section Order Matters for Scan Agent
**What goes wrong:** Scan agent processes sections in the wrong order or misses new sections.
**Why it happens:** Scan agent derives section list from `## ` headings in the template. If the template restructure isn't clean, the agent may not find all 7 sections.
**How to avoid:** Ensure the template has exactly 7 `## ` headings in the correct order: Overview, Key Concepts, Workflows, Getting Started, Common Tasks, Configuration, Troubleshooting. Each must have its comments.
**Warning signs:** Scan output for end-users has fewer than 7 source_material_index entries.

### Pitfall 5: Existing End-User Docs Must Be Deleted Before Regeneration
**What goes wrong:** Old 4-section USER_GUIDE.md from previous generation is partially overwritten, creating a hybrid document with old and new section structures.
**Why it happens:** Update mode preserves existing content for sections not in the update list.
**How to avoid:** Per locked decision: no migration. Old end-user docs are deleted, fresh generation with the new 7-section template. The generate command should detect template structure change or the user should run in initial mode for end-users after this update.
**Warning signs:** Generated USER_GUIDE.md has a mix of old (Getting Started with installation) and new (Overview, Key Concepts) sections.

### Pitfall 6: Config Persistence Race Condition
**What goes wrong:** Two concurrent scans write conflicting `user_interfaces` to `.docs.config.json`.
**Why it happens:** Multiple scan processes could theoretically run against the same project.
**How to avoid:** This is an edge case noted in existing patterns -- the pipeline already uses atomic writes via json_io.py. Since scans are typically single-threaded per-project, this is LOW risk.
**Warning signs:** Config has unexpected interface type after a scan.

### Pitfall 7: Exemplar Style vs Runtime Interface
**What goes wrong:** Writer copies exemplar content directly instead of adapting to detected interface.
**Why it happens:** Existing writer instruction says "Read the `<!-- EXAMPLE: ... -->` comment to understand what 'good' looks like" -- writers may copy web-UI exemplar style even when project is CLI-only.
**How to avoid:** Add explicit writer guidance: "Exemplars demonstrate web-UI style. If primary interface is CLI or API, follow same structure -- functional context before procedure, expected results after steps -- but use commands/responses instead of click paths."
**Warning signs:** CLI project gets "Click the Dashboard tab" instructions.

## Code Examples

### Schema Addition: user_interfaces in project_model

```json
"project_model": {
  "tech_stack": ["..."],
  "entry_points": ["..."],
  "components": ["..."],
  "infrastructure": {"..."},
  "user_interfaces": [
    {
      "type": "web",
      "name": "Road Runner Dashboard",
      "url_pattern": "/dashboard",
      "primary": true
    },
    {
      "type": "cli",
      "name": "rr CLI",
      "url_pattern": null,
      "primary": false
    }
  ]
}
```

The `user_interfaces` field is optional. When absent, writer falls back to CLI-style documentation (backward compatible with all existing projects).

### Schema Addition: synthesized_from on source_material_index entries

```json
"source_material_index": {
  "USER_GUIDE/overview": {
    "source_files": [],
    "staleness": "unknown",
    "synthesized_from": ["project_model.components", "project_model.user_interfaces"]
  },
  "USER_GUIDE/getting-started": {
    "source_files": ["src/routes/dashboard.py", "src/cli/main.py"],
    "staleness": "unknown"
  }
}
```

The `synthesized_from` field is optional. When present with empty `source_files`, it signals the writer to generate from project model fields instead of source files.

### Template Structure: New 7-Section USER_GUIDE

```markdown
<!-- DIATAXIS: how-to -->
<!-- AUDIENCE: end-users -->

# User Guide

## Overview
<!-- SYNTHESIZED: project_model.components, project_model.user_interfaces -->
<!-- PURPOSE: Introduce what this guide covers and what the reader will gain... -->
<!-- EXAMPLE: ... -->

## Key Concepts
<!-- SYNTHESIZED: project_model.components, project_model.entry_points -->
<!-- PURPOSE: Define domain + interaction concepts... -->
<!-- EXAMPLE: ... -->

## Workflows
<!-- SYNTHESIZED: project_model.entry_points, project_model.user_interfaces -->
<!-- PURPOSE: High-level journey maps... -->
<!-- EXAMPLE: ... -->

## Getting Started
<!-- BOUNDARY: Infrastructure setup belongs in devops/OPERATIONS.md, not here. -->
<!-- PURPOSE: Walk the user through their first interaction with the running system... -->
<!-- EXAMPLE: ... -->

## Common Tasks
<!-- PURPOSE: Cover the 3-5 operations users perform most frequently... -->
<!-- EXAMPLE: ... -->

## Configuration
<!-- BOUNDARY: System-level configuration belongs in devops/OPERATIONS.md. Only user-facing settings here. -->
<!-- PURPOSE: Document user-facing configuration options... -->
<!-- EXAMPLE: ... -->

## Troubleshooting
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Address the most common problems users encounter... -->
<!-- EXAMPLE: ... -->
```

### Scan Agent: SYNTHESIZED Parsing Logic

When the scan-audience agent encounters a SYNTHESIZED comment:

```
For each section heading:
  1. Read all HTML comments for this section
  2. If <!-- SYNTHESIZED: field1, field2 --> found:
     a. Split value on commas, trim whitespace -> field_list
     b. Skip source-file search entirely (no Glob/Grep)
     c. Write index entry:
        {
          "source_files": [],
          "staleness": "unknown",
          "synthesized_from": ["field1", "field2"]
        }
     d. MUST always produce the entry (its presence triggers writer synthesis)
  3. If <!-- BOUNDARY: text --> found:
     a. Record boundary text as exclusion guidance
     b. When searching for source files, exclude files matching boundary description
  4. Normal <!-- PURPOSE: ... --> processing continues for non-synthesized sections
```

### Writer Agent: Interface-Aware Generation

New step between "Read context" and "For each document":

```
2a. Read project_model.user_interfaces from scan data JSON.
    - If field is absent or empty array: set interface_style = "cli" (default)
    - Find the object with primary: true -> primary_interface
    - All other objects -> secondary_interfaces
    - Set interface_style based on primary_interface.type:
      - "web" -> click paths, form fields, screen states
      - "cli" -> commands, flags, terminal output
      - "api" -> requests, responses, status codes

2b. For each section, apply interface_style:
    - Before any procedure: explain the goal (what the user is accomplishing)
    - After the goal: explain what the system will do
    - Then steps through primary interface
    - If secondary_interfaces exist: add > **Power user tip:** callout
    - Expected results: what the user SEES (web: "appears in dashboard", cli: terminal output)
```

### End-User Exclusion Rules for Scan Agent

```
When audience == "end-users":

  EXCLUSIONS (NEVER index for end-user docs):
  - Package manifests: pyproject.toml, package.json, Cargo.toml
  - Database schemas/migrations: alembic/, migrations/
  - System service files: systemd/, Procfile, docker-compose.yml
  - CI configs: .github/, .gitlab-ci.yml
  - Environment files: .env, .env.example
  - Internal API modules
  - Test infrastructure: tests/, conftest.py

  INCLUSIONS (PREFER for end-user docs):
  - User-facing entry points
  - README usage sections
  - User config files
  - Workflow/flow definitions
  - Error message strings
  - UI templates
  - Route handlers
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 4-section template (Getting Started, Common Tasks, Config, Troubleshooting) | 7-section template (Overview, Key Concepts, Workflows, Getting Started, Common Tasks, Config, Troubleshooting) | Phase 15 | More complete user guide with orientation before procedures |
| CLI-only exemplars | Interface-aware exemplars (web-UI reference case) | Phase 15 | Writer adapts to project's actual interface instead of defaulting to bash |
| All source files eligible for end-user scan | Exclusion/inclusion rules for end-user audience | Phase 15 | Prevents infrastructure code from polluting user documentation |
| Sections always backed by source files | SYNTHESIZED sections from project model fields | Phase 15 | Enables overview/concepts/workflows sections that don't map to specific files |
| No negative guidance | BOUNDARY comments prevent wrong-audience content | Phase 15 | Prevents installation/infrastructure from appearing in user guide |

## Open Questions

1. **BOUNDARY comments for non-end-user templates**
   - What we know: CONTEXT.md lists this as Claude's Discretion
   - What's unclear: Whether devops, developer, or agent templates would benefit from BOUNDARY comments in Phase 15
   - Recommendation: Add BOUNDARY comments only to the USER_GUIDE template in Phase 15. If other templates need them, they can be added in a future phase. This keeps scope tight.

2. **Ambiguous heuristic detection (multiple equally-likely interfaces)**
   - What we know: CONTEXT.md lists this as Claude's Discretion
   - What's unclear: What to do when heuristics detect both web and CLI with equal confidence
   - Recommendation: Present both to user via AskUserQuestion with a note: "Multiple interfaces detected with similar confidence. Please confirm which is primary." If non-interactive, fall back to no user_interfaces (CLI default).

3. **How generate handles the "delete old docs" requirement (EUQ-05)**
   - What we know: Locked decision says "Old end-user docs simply deleted, fresh generation"
   - What's unclear: Whether the generate command needs modification to support this, or if running in initial mode for end-users is sufficient
   - Recommendation: No generate command changes needed. After Phase 15 template updates, the next `auto-doc-generate` run in initial mode naturally produces a fresh USER_GUIDE.md with the new 7-section structure. In update mode, the structurally incompatible old sections won't match new template headings, so the entire document will be treated as needing regeneration. Document this in the plan as a usage note, not a code change.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `python3 -m pytest`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header` |
| Full suite command | `python3 -m pytest --tb=short -q --no-header` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EUQ-01 | Interface detection + config persistence | manual-only | N/A -- scan is LLM orchestration, not Python code | N/A |
| EUQ-02 | Writer interface-aware generation | manual-only | N/A -- writer is an LLM agent prompt, not Python code | N/A |
| EUQ-03 | End-user scan exclusion rules | manual-only | N/A -- scan-audience.md is an LLM prompt, not Python code | N/A |
| EUQ-04 | Template 7-section structure | manual-only | N/A -- template is a markdown file, validate by visual inspection | N/A |
| EUQ-05 | Old docs deleted + fresh generation | manual-only | N/A -- generate behavior, not script logic | N/A |
| EUQ-06 | SYNTHESIZED section support | unit (partial) | `python3 -m pytest auto-doc/scripts/tests/test_write_scan_output.py -x` | Existing (covers key validation) |
| EUQ-07 | BOUNDARY comment support | manual-only | N/A -- agent prompt behavior | N/A |
| EUQ-08 | Functional-first pattern | manual-only | N/A -- writer prompt behavior | N/A |
| EUQ-09 | Cross-audience boundaries | manual-only | N/A -- template + agent prompt behavior | N/A |
| EUQ-10 | DOMAIN_SPECIFIC deletion | unit | Verify file does not exist after deletion | N/A |

### Sampling Rate
- **Per task commit:** `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header`
- **Per wave merge:** `python3 -m pytest --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

None -- existing test infrastructure covers all phase requirements. This phase primarily modifies LLM prompt files (markdown), not Python scripts. The existing `write-scan-output.py` tests already validate key format acceptance which covers EUQ-06's data path. No new Python scripts are introduced, so no new test files are needed.

**Verification strategy for prompt-based changes:** Since most requirements are LLM agent behavior changes (not Python code), verification relies on:
1. Structural validation: template has exactly 7 `## ` headings with correct comment types
2. Schema validation: schema.md documents new fields with examples
3. Agent instruction review: scan-audience.md and end-user-writer.md contain explicit handling for SYNTHESIZED, BOUNDARY, and interface-aware generation
4. Existing test suite passing: confirms no regressions in Python scripts that pass through the new fields

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection of all files listed in Architecture Patterns section
- CONTEXT.md locked decisions (user-verified requirements)
- schema.md, scan-audience.md, end-user-writer.md, auto-doc-scan.md, USER_GUIDE.template.md (current state verified via Read tool)

### Secondary (MEDIUM confidence)
- staleness-check.py line 149-150 behavior confirmed via Read tool (returns None for empty sources)
- write-scan-output.py key validation regex confirmed via Read tool (accepts standard DOCUMENT/section-slug format)
- merge-scan.py project_model passthrough confirmed via Read tool (takes from first file that has it)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all files are in the codebase, changes are well-specified by CONTEXT.md locked decisions
- Architecture: HIGH -- patterns extend existing HTML comment system and scan/writer agent contract
- Pitfalls: HIGH -- derived from direct code analysis of existing validation, parsing, and generation logic

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable -- changes are to this project's own files, not external dependencies)
