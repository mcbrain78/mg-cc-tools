# Phase 23: Template Refiner Pipeline - Research

**Researched:** 2026-04-02
**Domain:** LLM pipeline orchestration, markdown template generation, agent spawning patterns, HTML comment conventions
**Confidence:** HIGH

## Summary

Phase 23 creates two new files -- a `prepare-templates.md` command and a `template-refiner.md` agent -- that together form a new pipeline step between scan and generate. The command reads scan data (`docs-scan.json`) and generic templates, then spawns one refiner agent per document. Each refiner agent performs shallow source exploration (symbol overviews for Python, full reads for config/infrastructure files) and produces a refined template with project-specific `###`/`####` headings, PURPOSE comments containing structural facts, and generic EXAMPLE blocks demonstrating format only.

This phase produces no Python scripts. The deliverables are two markdown files: a command orchestrator and an agent definition. The refined templates are written to `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` by the refiner agent using the Write tool. The command follows the established agent-per-document spawning pattern used by `auto-doc-generate.md`, and the agent follows the `TEMPLATE.md` pattern used by all writer agents.

The downstream consumer is Phase 24 (writer orient-write integration), which modifies `generate-setup.py` to detect refined templates and modifies the devops-writer to use the orient-write loop via `next-heading.py` (already built in Phase 22). Phase 23's output format must be parseable by `next-heading.py`'s `parse_template()` function, which expects `##`-`####` headings with `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` HTML comments.

**Primary recommendation:** Build `prepare-templates.md` as a command that loads config + scan data, discovers audience/document pairs, and spawns one Agent call per document with the refiner agent. Build `template-refiner.md` as an agent that reads the generic template, reads scan data sections, performs shallow source exploration per `##` section, and writes a complete refined template with resolved OPTIONAL markers, project-specific PURPOSE comments, and generic structural EXAMPLE blocks.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- New command: `/mg:auto-doc-prepare-templates` orchestrating template refinement
- Reads scan data: `project_model`, `source_material_index`, `gap_analysis` from `docs-scan.json`
- For each audience/document, reads the generic template to get `##` sections with PURPOSE/EXAMPLE
- Spawns a refiner agent per document
- Outputs refined templates to `.mg/docs/templates/{audience}/{DOCUMENT}.template.md`
- Produces refined templates for all configured audiences -- writers that cannot consume refined templates (end-user, developer, agent) ignore them via generate command's fallback logic
- One refiner agent spawned per document
- Agent does shallow source exploration on source files listed in `source_material_index` for each `##` section:
  - `get_symbols_overview` on Python files -- public API names, class names, no function bodies
  - Full reads for non-code files -- systemd units, alembic configs, YAML configs, .env.example
  - NOT reading function bodies, NOT understanding implementation logic
- Decides what `###`/`####` headings each `##` section needs based on scan data and source findings
- Writes a PURPOSE comment per heading -- project-specific, grounded in scan data and shallow source reading
- Writes a generic structural EXAMPLE per heading -- format demonstration only (table columns, step format, list style), no project-specific values
- Refined template is a complete replacement for the generic template -- writer sees only the refined template, not both
- `<!-- DIATAXIS: ... -->` and `<!-- AUDIENCE: ... -->` comments preserved from generic template
- `<!-- REFINED: {date}, scan: {date} -->` metadata tracks generation date and source scan date
- `##` sections preserve the same slugs and structure from generic template -- refiner does NOT rename or reorganize `##` sections
- `###`/`####` headings added with project-specific `<!-- PURPOSE: ... -->` and generic `<!-- EXAMPLE: ... -->` HTML comments
- OPTIONAL markers from generic template resolved -- sections either become concrete headings or are dropped based on scan findings
- EXAMPLE blocks demonstrate format only -- writer fills concrete values from source code
- PURPOSE comments are project-specific -- contain structural facts (counts, names, relationships) verifiable from symbol overviews and config reads
- EXAMPLE blocks are generic -- format demonstrations with placeholder data, no project-specific values
- `prepare-templates` overwrites refined templates by default on re-run -- no merge logic
- Refined templates are derived artifacts -- same scan data produces same output
- Refined templates written to `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` (new project-local directory)
- Template idempotency: run prepare-templates twice on same scan data -- output refined templates should be structurally equivalent

### Claude's Discretion
- Agent prompt structure and tool allowlist for the template-refiner agent
- How the command discovers which audiences/documents to process (from scan data, config, or generic template directory listing)
- Internal organization of the prepare-templates command (sequential vs parallel refiner spawning)
- How the refiner decides to drop vs keep OPTIONAL sections -- threshold or heuristic
- Error handling when scan data is missing or generic templates can't be found
- Whether the refiner agent uses Serena tools or standard Read for source exploration

### Deferred Ideas (OUT OF SCOPE)
- Merge mode for refined templates -- overwrite only for now, merge adds complexity for a rare use case
- Per-heading source file assignment in the scan -- source files stay at `##` granularity
- Automatic prepare-templates invocation from generate -- it's a separate manual command
- Stale writer modernization -- end-user-writer, developer-writer, agent-writer are not on the current writer format and are not updated here
- Glossary and overview writer changes -- these writers don't consume audience-specific templates with heading trees
- Parallel heading writes -- sequential loop is simpler and sufficient
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRF-01 | Running `/mg:auto-doc-prepare-templates` reads scan data and produces per-audience refined templates at `.mg/docs/templates/{audience}/{DOCUMENT}.template.md`, overwriting any previous versions | Command reads config for audience/document discovery, loads scan data, spawns refiner agents, agents write refined templates via Write tool to output directory |
| TRF-02 | Each refiner agent performs shallow source exploration (symbol overviews for code, full reads for config files) and decides what `###`/`####` headings each `##` section needs | Agent reads source files from `source_material_index` entries per `##` section; uses `get_symbols_overview` for Python, Read for non-code files; structural findings drive heading decisions |
| TRF-03 | PURPOSE comments in refined template headings contain project-specific structural facts (counts, names, relationships) grounded in scan data and source exploration | Agent extracts structural facts from symbol overviews (class count, API surface) and config reads (service names, schema counts); writes these as `<!-- PURPOSE: ... -->` comments |
| TRF-04 | EXAMPLE blocks in refined template headings are generic format demonstrations with placeholder data, containing no project-specific values | Agent preserves generic EXAMPLE format from generic template for `##` sections, creates new generic structural EXAMPLEs for `###`/`####` headings with `...` placeholders |
| TRF-05 | `##` sections preserve the same slugs and structure from the generic template -- the refiner does not rename or reorganize top-level sections | Agent reads generic template `##` headings verbatim, preserves their text and order, only adds children beneath them |
| TRF-06 | The refined template fully replaces the generic template for the writer -- the writer sees only the refined version | Refined template includes all metadata (`DIATAXIS`, `AUDIENCE`, `REFINED`), carries forward all `##` sections from generic, and adds `###`/`####` structure -- writer needs no other template |
| TRF-07 | Running `prepare-templates` twice on the same scan data produces structurally equivalent refined templates (same heading tree, same PURPOSE topics) | Idempotency follows from deterministic inputs: same scan data + same generic template + same source files = same heading decisions. Agent prompt should instruct deterministic structural decisions based on source evidence |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Agent tool | Claude Code built-in | Spawn refiner subagent per document | Same pattern as generate command spawning writer agents |
| Write tool | Claude Code built-in | Refiner writes refined template to output path | Standard for all file creation in auto-doc pipeline |
| Read tool | Claude Code built-in | Refiner reads generic templates, config, scan data | Standard for agent file I/O |
| Glob tool | Claude Code built-in | Discover generic template files | Standard for file discovery |
| Bash tool | Claude Code built-in | Run Python scripts (list-optional-sections.py) | Standard for script invocation |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `list-optional-sections.py` | Existing | Identify which `##` sections are OPTIONAL in generic templates | Command can pre-compute optional sections to pass to refiner |
| `get-section-sources.py` | Existing | Look up source files for a section from scan data | Refiner can use to get source file lists per `##` section |
| Serena `get_symbols_overview` | Available | Shallow symbol exploration of Python files | Refiner uses for structural understanding of source code |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Agent per document | Agent per audience | Per-document gives more focused context per refiner call, matches generate command pattern |
| Serena tools for source exploration | Standard Read for all files | Serena's `get_symbols_overview` is more token-efficient for Python files; Read is needed for non-code files regardless |
| Sequential agent spawning | Parallel agent spawning | Sequential is simpler, parallel saves time but adds complexity to error handling; Claude's Discretion |

## Architecture Patterns

### Recommended Project Structure
```
auto-doc/
├── commands/
│   └── auto-doc-prepare-templates.md    # NEW: orchestrator command
├── agents/
│   └── template-refiner.md              # NEW: refiner agent
└── ...existing files...

# Output at runtime (in target project):
.mg/docs/templates/
├── end-users/
│   └── USER_GUIDE.template.md
├── developers/
│   ├── ARCHITECTURE.template.md
│   ├── DEVELOPER_GUIDE.template.md
│   └── QUICK_REFERENCE.template.md
├── agents/
│   ├── SYSTEM_MAP.template.md
│   ├── CONVENTIONS.template.md
│   ├── GOTCHAS.template.md
│   └── TESTING.template.md
└── devops/
    ├── OPERATIONS.template.md
    └── TROUBLESHOOTING.template.md
```

### Pattern 1: Command Orchestrator (prepare-templates.md)

**What:** A command file that loads configuration, reads scan data, and spawns one Agent call per audience/document pair.

**When to use:** Follows the exact pattern of `auto-doc-generate.md` Stage 2 (writer spawning).

**Structure:**
1. Load config (`.mg/docs/.docs.config.json` with `{GLOBAL_CONFIG}` fallback)
2. Read scan data from `.mg/docs/docs-scan.json` (extract `scan_date`, `project_model`, `source_material_index`, `gap_analysis`)
3. Discover audiences and documents from config
4. For each audience/document pair:
   - Locate generic template at `{TEMPLATES_DIR}/{audience}/{DOCUMENT}.template.md`
   - Spawn Agent with template-refiner instructions
5. Create output directories `mkdir -p .mg/docs/templates/{audience}/`
6. Report summary

**Key detail:** The command must pass the following to each refiner agent via the Agent prompt:
- `project_root`: absolute path
- `generic_template_path`: path to the generic template for this document
- `scan_data_path`: path to `docs-scan.json`
- `output_path`: exact path where the refined template should be written
- `audience`: audience name
- `document`: document name
- `scan_date`: from scan data (for `<!-- REFINED: -->` metadata)
- `project_model_path`: where to read the project model from (or inline in prompt)

### Pattern 2: Refiner Agent (template-refiner.md)

**What:** An agent spawned per document that produces a refined template.

**When to use:** Each invocation handles one document's template.

**Structure:**
1. Read the generic template (passed as path)
2. Extract `##` sections, their headings, PURPOSE, EXAMPLE, and OPTIONAL markers
3. Read scan data for this document's source_material_index entries
4. For each `##` section:
   a. Look up source files from `source_material_index` using `{DOCUMENT}/{section-slug}` key
   b. Perform shallow source exploration on those files:
      - Python files: `get_symbols_overview` (Serena) or file-level Read for non-parseable
      - Non-code files: full Read (systemd units, YAML, .env.example, alembic configs, etc.)
   c. Based on findings, decide `###`/`####` headings needed
   d. If the section has `<!-- OPTIONAL -->`: check if source material exists -- if yes, keep and add children; if no, drop the section entirely
5. Compose the refined template:
   - Preserve `<!-- DIATAXIS: -->` and `<!-- AUDIENCE: -->` from generic
   - Add `<!-- REFINED: {date}, scan: {scan_date} -->`
   - Preserve `# Title` from generic
   - For each `##` section: rewrite PURPOSE to be project-specific, keep or adapt EXAMPLE to be generic/structural
   - For each new `###`/`####`: add project-specific PURPOSE and generic structural EXAMPLE
6. Write the complete refined template to `output_path`

### Pattern 3: Existing Agent Spawning Pattern (from generate command)

**What:** The generate command already spawns one agent per audience. The prepare-templates command follows the same pattern but spawns one agent per document (finer granularity because each document maps to one template).

**Example from auto-doc-generate.md Stage 2:**
```
Agent(
  description="Generate {audience} documentation",
  prompt="You are the {audience} writer agent.

  Read and follow the instructions in: {AGENTS_DIR}/{audience}-writer.md

  Project root: {project_root}
  Docs dir: {docs_dir_abs}
  ..."
)
```

The prepare-templates command follows this same pattern:
```
Agent(
  description="Refine templates for {audience}/{DOCUMENT}",
  prompt="You are the template refiner agent.

  Read and follow the instructions in: {AGENTS_DIR}/template-refiner.md

  Project root: {project_root}
  Generic template: {TEMPLATES_DIR}/{audience}/{DOCUMENT}.template.md
  Scan data: .mg/docs/docs-scan.json
  Output path: .mg/docs/templates/{audience}/{DOCUMENT}.template.md
  Audience: {audience}
  Document: {DOCUMENT}
  Scan date: {scan_date}
  ..."
)
```

### Pattern 4: Refined Template Output Format

**What:** The refined template format that `next-heading.py` (Phase 22) already parses.

**Critical compatibility constraint:** The `parse_template()` function in `next-heading.py` expects:
- `##`-`####` headings as markdown heading lines (not inside HTML comments)
- `<!-- PURPOSE: content -->` multi-line HTML comments after headings
- `<!-- EXAMPLE: content -->` multi-line HTML comments after headings
- Headings inside EXAMPLE blocks are already handled (stripped via comment range detection)

**Example refined template (from concept doc):**
```markdown
<!-- DIATAXIS: how-to + reference -->
<!-- AUDIENCE: devops -->
<!-- REFINED: 2026-04-02, scan: 2026-04-01 -->

# Operations Guide

## Infrastructure Overview
<!-- PURPOSE: Operators need a single-page mental model of the system's
     deployment topology. 3 systemd services on a single host, PostgreSQL
     on a separate host, Prefect orchestration layer. -->

### Deployment Topology
<!-- PURPOSE: Component-to-host mapping. 3 systemd services (prefect-server,
     finance-data-worker, stock-ranker-worker) plus PostgreSQL on mcbrain-server2. -->
<!-- EXAMPLE:
| Component | Service Unit | Host | Port | Health Check |
|-----------|-------------|------|------|-------------|
| ... | ... | ... | ... | ... |
-->

### External Dependencies
<!-- PURPOSE: 4 external API clients (FMP, FINRA, SEC EDGAR, Google AI)
     with rate limits, timeouts, and fallback behavior. -->
<!-- EXAMPLE:
| Service | Purpose | Client Class | Rate Limit | Fallback |
|---------|---------|-------------|------------|----------|
| ... | ... | ... | ... | ... |
-->
```

### Anti-Patterns to Avoid

- **Refiner renaming `##` sections:** The refiner MUST preserve `##` heading text and order exactly from the generic template. Changing headings breaks `source_material_index` key matching (`{DOCUMENT}/{section-slug}`).
- **Project-specific values in EXAMPLE blocks:** EXAMPLE blocks must use `...` placeholders and generic column headers. Project-specific content goes ONLY in PURPOSE comments.
- **Reading function bodies:** The refiner's shallow exploration must NOT read function implementations. `get_symbols_overview` returns class/function names and signatures -- that is the ceiling.
- **Embedding Python in the agent:** Per CLAUDE.md convention, all deterministic logic goes in scripts. However, this phase has no deterministic logic that warrants a script -- the refiner's work is inherently LLM-driven (deciding heading structure from source exploration).
- **Skipping `<!-- REFINED: -->` metadata:** The refined template MUST include the `<!-- REFINED: {date}, scan: {scan_date} -->` comment. Phase 24's generate command uses this to detect stale templates.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Discovering audiences/documents | Custom file walking | Config file (`.docs.config.json`) | Config already lists all audiences with their documents; same source of truth as generate |
| Identifying OPTIONAL sections | Manual template parsing | `list-optional-sections.py` | Already exists, returns JSON array of `DOCUMENT/section-slug` for OPTIONAL sections |
| Looking up source files per section | Manual scan JSON parsing | `get-section-sources.py` | Already exists, returns source files for a given `DOCUMENT/section-slug` key |
| Slugifying headings | Custom slug logic | Existing `slugify_heading()` convention | Slug format must match write-section.py and next-heading.py exactly |
| Template output directory creation | Complex directory logic | Simple `mkdir -p .mg/docs/templates/{audience}/` | Bash mkdir handles existence check |

**Key insight:** This phase creates two LLM instruction files (command + agent), not Python scripts. The existing script infrastructure (`list-optional-sections.py`, `get-section-sources.py`) provides the deterministic operations the refiner needs. The refiner's core work -- deciding heading structure from shallow source exploration -- is inherently LLM-driven.

## Common Pitfalls

### Pitfall 1: Slug Mismatch Between Generic and Refined Templates
**What goes wrong:** If the refiner changes `##` heading text (even slightly -- capitalization, punctuation), the slug changes, and `source_material_index` lookups fail silently (no match = no source files).
**Why it happens:** The LLM might "improve" heading text or normalize it.
**How to avoid:** The agent prompt must contain an explicit MUST NOT rule: "Do NOT rename, reword, or reorganize `##` section headings. Copy them verbatim from the generic template."
**Warning signs:** `next-heading.py` orient responses with empty `source_files` arrays when source material should exist.

### Pitfall 2: Project-Specific Values Leaking into EXAMPLE Blocks
**What goes wrong:** The refiner, having read source files for PURPOSE comments, accidentally includes project-specific names, counts, or values in EXAMPLE blocks.
**Why it happens:** The LLM has the project context in memory when writing EXAMPLE blocks.
**How to avoid:** Explicit instruction in agent prompt: "EXAMPLE blocks use `...` placeholders and generic column headers. They demonstrate format (table layout, step structure), never project-specific values. All project-specific information belongs ONLY in PURPOSE comments."
**Warning signs:** EXAMPLE blocks containing real project class names, file paths, or service names.

### Pitfall 3: Headings Inside EXAMPLE Blocks Parsed as Real Headings
**What goes wrong:** If EXAMPLE blocks contain heading syntax (`###`, `####`), downstream parsers might treat them as real template headings.
**Why it happens:** EXAMPLE blocks naturally demonstrate heading formats.
**How to avoid:** `next-heading.py` already handles this -- its `parse_template()` strips HTML comment ranges before heading detection. But the refiner agent should still avoid putting heading lines inside EXAMPLE blocks where possible. When unavoidable (demonstrating heading format), they are safely inside `<!-- EXAMPLE: ... -->` comment blocks.
**Warning signs:** `next-heading.py` producing more headings than expected.

### Pitfall 4: OPTIONAL Section Resolution Without Sufficient Evidence
**What goes wrong:** The refiner drops an OPTIONAL section because it finds no source material, but the section is actually relevant -- the scan just didn't index the right files.
**Why it happens:** Source material coverage depends on scan quality, which varies.
**How to avoid:** Conservative heuristic: keep OPTIONAL sections if ANY evidence exists (source files in index, relevant entries in project_model, related components). Only drop if there is no evidence at all.
**Warning signs:** Refined templates missing sections that have source material in `source_material_index`.

### Pitfall 5: install.sh Not Updated for New Command and Agent
**What goes wrong:** The new command and agent files are created but not registered in install.sh, so they don't get deployed to target projects.
**Why it happens:** Forgetting to add the new command name to the COMMANDS array and ensure the agent file gets copied.
**How to avoid:** Add `auto-doc-prepare-templates` to the COMMANDS array in install.sh. The agent file (`template-refiner.md`) is automatically copied by the existing `agents/*.md` wildcard in install.sh. Verify sed resolution handles any placeholders used in the new files.
**Warning signs:** `/mg:auto-doc-prepare-templates` not available after install.

### Pitfall 6: Non-Idempotent Heading Decisions
**What goes wrong:** Running prepare-templates twice on the same scan data produces different heading structures because the LLM makes non-deterministic choices.
**Why it happens:** Heading decisions are LLM-driven, and temperature/sampling can vary.
**How to avoid:** Agent prompt should instruct evidence-based heading decisions: "Create a heading only when source evidence supports it. Document the evidence in the PURPOSE comment. The same evidence should produce the same heading." This minimizes structural variation.
**Warning signs:** Diff between two runs shows different heading counts or topics for the same `##` section.

### Pitfall 7: Shared Templates (OVERVIEW, GLOSSARY) Getting Refined Unnecessarily
**What goes wrong:** The command tries to refine OVERVIEW or GLOSSARY templates, but these are shared documents that don't belong to any audience and aren't consumed by the orient-write loop.
**Why it happens:** The config includes `shared_documents: ["OVERVIEW", "GLOSSARY"]` which could be mistakenly processed.
**How to avoid:** The command should only process audience-specific documents from `config.audiences.{audience}.documents`, not `config.shared_documents`. The concept doc is clear: glossary-writer and overview-writer don't consume audience-specific templates.
**Warning signs:** Refined templates appearing for OVERVIEW.template.md or GLOSSARY.template.md.

## Code Examples

### Example 1: Command Discovery Loop

The prepare-templates command iterates audience/document pairs from config:

```
# Pseudo-structure for prepare-templates.md

For each audience in config.audiences:
  if not audience.enabled: skip
  for each document in audience.documents:
    generic_template = {TEMPLATES_DIR}/{audience}/{document}.template.md
    output_path = .mg/docs/templates/{audience}/{document}.template.md

    Agent(
      description="Refine template for {audience}/{document}",
      prompt="... template-refiner instructions ..."
    )
```

### Example 2: Refiner Agent Source Exploration Pattern

The refiner performs shallow exploration per `##` section:

```
# For each ## section in the generic template:
1. Look up source files: get-section-sources.py --scan-file ... --key "{DOCUMENT}/{section-slug}"
2. For each source file:
   - If .py file: get_symbols_overview (Serena) -> class names, function signatures
   - If .service/.yaml/.toml/.env/.cfg/.ini/.conf/.sql file: Read (full content)
   - If .md file: Read (full content)
3. From the structural findings, decide:
   - What ### headings are needed (e.g., 3 systemd services -> "Service Units" heading)
   - What #### headings under those (e.g., per-service details if >3 services)
   - What counts/names to include in PURPOSE (e.g., "3 systemd services: prefect-server, ...")
```

### Example 3: OPTIONAL Section Resolution

```
# The generic template has:
## Monitoring & Alerting
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: What to monitor... -->

# The refiner checks:
1. Does source_material_index have entries for "{DOCUMENT}/monitoring-alerting"?
2. Does project_model.infrastructure mention monitoring tools?
3. Do source files include monitoring configs, health check endpoints?

# If ANY evidence: keep the section, add ### headings
# If NO evidence at all: drop the section entirely from refined template
```

### Example 4: Refined Template Metadata

```markdown
<!-- DIATAXIS: how-to + reference -->
<!-- AUDIENCE: devops -->
<!-- REFINED: 2026-04-02, scan: 2026-04-01 -->

# Operations Guide
```

The `REFINED` comment uses the current date and the `scan_date` from `docs-scan.json`. Phase 24 uses this to detect stale refined templates (when `scan_date` in docs-scan.json is newer than `scan:` in the REFINED comment).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Writer decides all `###`/`####` structure | Refiner pre-decides heading structure | Phase 23 (this phase) | Writer focuses on content, not structure |
| Generic template used directly by writer | Refined template replaces generic for writer | Phase 23 (this phase) | Project-specific heading guidance |
| No `<!-- REFINED: -->` metadata | Templates track refinement and scan dates | Phase 23 (this phase) | Stale template detection possible |
| OPTIONAL sections resolved by writer at generate time | OPTIONAL sections resolved by refiner at prepare time | Phase 23 (this phase) | Consistent section inclusion/exclusion |

## Open Questions

1. **Serena vs Read for source exploration**
   - What we know: The CONTEXT.md lists this as Claude's Discretion. Serena's `get_symbols_overview` is more token-efficient for Python files (returns class/function names without bodies). Read is required for non-code files.
   - What's unclear: Whether the refiner agent's allowed-tools should include Serena tools (requires the project to have Serena configured) or stick to Read only.
   - Recommendation: Use Serena tools when available (they are listed in the project's MCP servers). The refiner agent should use `get_symbols_overview` for Python files and `Read` for everything else. If Serena is not available, fall back to Read for Python files (scan overview-level content from the file, not deep reading).

2. **Sequential vs Parallel Agent Spawning**
   - What we know: The CONTEXT.md lists this as Claude's Discretion. There are 10 audience documents across 4 audiences. Sequential spawning is simpler.
   - What's unclear: Whether sequential spawning of 10 refiner agents will be slow enough to matter in practice.
   - Recommendation: Sequential spawning. Each refiner agent is a moderate-size task (read generic template, explore 5-15 source files, write one refined template). The total time is manageable, and sequential avoids race conditions on shared scan data reads. If performance is a concern, audiences can be parallelized (4 parallel groups of 1-4 documents).

3. **Agent Tool Allowlist**
   - What we know: The refiner needs Read (generic template, scan data, non-code source files), Write (refined template output), Bash (script invocation for `get-section-sources.py`, `list-optional-sections.py`), and Glob (discovering source files if needed). It may also use Serena tools (`get_symbols_overview`, `find_symbol`).
   - Recommendation: `allowed-tools: Read, Write, Bash, Glob, Grep` for the command. The refiner agent (spawned via Agent tool) inherits tools from the parent -- standard pattern in auto-doc.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` |
| Quick run command | `uv run python -m pytest auto-doc/scripts/tests/ -x --tb=short -q` |
| Full suite command | `uv run python -m pytest --tb=short -q --no-header` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRF-01 | Command reads scan data and produces refined templates | manual-only | N/A -- this is a markdown command file, behavior is LLM-driven | N/A |
| TRF-02 | Refiner performs shallow source exploration and decides headings | manual-only | N/A -- LLM-driven agent behavior | N/A |
| TRF-03 | PURPOSE comments contain project-specific structural facts | manual-only | N/A -- LLM-driven content quality | N/A |
| TRF-04 | EXAMPLE blocks are generic format demonstrations | manual-only | N/A -- LLM-driven content quality | N/A |
| TRF-05 | `##` sections preserve slugs from generic template | manual-only | N/A -- LLM-driven structural preservation | N/A |
| TRF-06 | Refined template fully replaces generic for writer | smoke | Verify refined template is parseable by next-heading.py parse_template() | Covered by existing test_next_heading.py |
| TRF-07 | Idempotent heading structure on re-run | manual-only | N/A -- requires two LLM runs and structural comparison | N/A |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest auto-doc/scripts/tests/test_next_heading.py -x --tb=short -q` (verify refined template format compatibility)
- **Per wave merge:** `uv run python -m pytest --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
None -- this phase creates markdown files (command + agent), not Python scripts. The existing `test_next_heading.py` already validates that `parse_template()` correctly handles the refined template format. No new test files are needed because there is no new Python code to test.

## Sources

### Primary (HIGH confidence)
- Existing codebase analysis: `auto-doc/commands/auto-doc-generate.md` (agent spawning pattern)
- Existing codebase analysis: `auto-doc/agents/TEMPLATE.md` (writer agent structure)
- Existing codebase analysis: `auto-doc/agents/devops-writer.md` (per-document agent pattern)
- Existing codebase analysis: `auto-doc/scripts/next-heading.py` (parse_template() format requirements)
- Existing codebase analysis: `auto-doc/references/templates/devops/OPERATIONS.template.md` (generic template format)
- Existing codebase analysis: `auto-doc/references/.docs.config.json` (audience/document configuration)
- Existing codebase analysis: `auto-doc/references/schema.md` (source_material_index format)
- Existing codebase analysis: `auto-doc/install.sh` (command registration and agent deployment)

### Secondary (MEDIUM confidence)
- `docs/work-queue/todo/prepare-templates/concept.md` (design concept with example refined template)
- `docs/work-queue/todo/prepare-templates/phase-docs/phase-23-template-refiner-pipeline.md` (phase scope doc)
- Phase 22 CONTEXT.md and RESEARCH.md (next-heading.py spec that consumes refined templates)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all patterns exist in the codebase (agent spawning, template format, scan data access)
- Architecture: HIGH -- follows existing auto-doc pipeline patterns exactly
- Pitfalls: HIGH -- identified from direct codebase analysis and understanding of slug matching, OPTIONAL resolution, and install.sh patterns

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (30 days -- stable codebase patterns)
