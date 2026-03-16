# Phase 2: Templates & Agent Definitions - Research

**Researched:** 2026-03-16
**Domain:** LLM documentation templates and agent prompt definitions for a multi-audience documentation pipeline
**Confidence:** HIGH

## Summary

Phase 2 is a content authoring phase -- no Python scripts, no complex infrastructure. The deliverables are ~13 Markdown template files and 7+1 agent definition files (the "+1" being a shared TEMPLATE.md). All content follows locked design decisions from the CONTEXT.md: three-layer template architecture (classification + structure + exemplar), four audience-specific writer agents, plus glossary, staleness, and verifier agents. The codebase-health tool provides the reference implementation pattern for agent definitions.

The primary technical challenge is not code complexity but consistency and quality at scale: 13 templates each need purpose statements and exemplars for every section, and 7 agents each need complete operational instructions. The secondary challenge is an install.sh gap: the current install.sh does not copy the `references/templates/` directory tree, only individual reference files. This must be patched as part of Phase 2.

**Primary recommendation:** Organize work by deliverable type (templates first, then agents), with templates split by audience. Each plan wave produces files that can be verified by reading them -- no runtime tests needed. The install.sh patch should be a final task after all content files exist.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Three-Layer Template Architecture: Layer 1 (Diataxis classification), Layer 2 (structural headings with purpose statements), Layer 3 (concrete exemplar per section). HTML comments for purpose/example that are stripped from final output.
- Template file format: Markdown with `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` HTML comments
- Optional sections marked with `<!-- OPTIONAL -- delete if not applicable -->`
- No word count constraints
- Template inventory: 13 templates organized by audience subdirectory under `references/templates/`
- Shared: OVERVIEW.template.md, GLOSSARY.template.md
- End-users: USER_GUIDE.template.md, DOMAIN_SPECIFIC.template.md
- Developers: ARCHITECTURE.template.md, DEVELOPER_GUIDE.template.md, QUICK_REFERENCE.template.md
- Agents: SYSTEM_MAP.template.md, CONVENTIONS.template.md, GOTCHAS.template.md, TESTING.template.md
- DevOps: OPERATIONS.template.md, TROUBLESHOOTING.template.md
- End-User Writer Agent (AGT-01): plain language, scannable, numbered steps max 7, task-oriented
- Developer Writer Agent (AGT-02): code-first Stripe/Twilio style, Diataxis separation, "I want to..." lookups
- Agent Writer Agent (AGT-03): YAML frontmatter, explicit over implicit, Codified Context architecture, tables for structured data
- DevOps Writer Agent (AGT-04): runbook structure, copy-paste-ready commands, decision trees, rollback procedures
- Glossary Writer Agent (AGT-05): terminology reconciliation, receives proposed terms from writers
- Staleness Scanner Agent (AGT-06): per-section freshness analysis for scan pipeline
- Verifier Agent (AGT-07): cross-reference, Diataxis, completeness checking for verify pipeline
- Parallel execution (AGT-08): execution order is (1) glossary agent first, (2) 4 writer agents in parallel, (3) glossary reconciliation pass, (4) OVERVIEW.md last
- Agents receive file paths only, read files themselves -- no pasting of templates/source material into agent prompts
- Writers propose terms only (term + one-line context note), glossary agent writes all definitions
- Tool installs to `.claude/create-docs/` -- templates at `.claude/create-docs/references/templates/`, agents at `.claude/create-docs/agents/`
- Road-runner validation baked into phase success criteria

### Claude's Discretion
- Internal structure of each agent prompt (how to organize instructions within each .md file)
- TEMPLATE.md shared pattern design -- how to structure the common pattern all writers follow
- Exact exemplar content for each template section (the "Layer 3" creative work)
- How staleness-scanner and verifier agents integrate with their respective pipeline steps

### Deferred Ideas (OUT OF SCOPE)
- Testing strategy for agent prompt quality -- cross-cutting open item
- Template versioning (for future updates) -- not in v1 scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TPL-01 | Three-layer template architecture: Diataxis classification + structural headings with purpose + exemplar per section | Template format pattern documented in Architecture Patterns; Diataxis principles verified from official source |
| TPL-02 | ~13 audience-organized templates in references/templates/ matching each document type | Full template inventory mapped; directory structure defined |
| TPL-03 | Optional section markers (prevent empty boilerplate in generated docs) | `<!-- OPTIONAL -->` pattern documented; applies to templates with audience-dependent content |
| AGT-01 | End-user writer agent with plain language, scannable formatting conventions | Agent definition pattern from codebase-health TEMPLATE.md; format conventions from CONTEXT.md decisions |
| AGT-02 | Developer writer agent with code-first, Stripe/Twilio-style conventions | Same agent pattern; code-first conventions locked |
| AGT-03 | Agent writer agent with explicit, machine-optimized conventions and YAML frontmatter | Same agent pattern; Codified Context three-tier architecture locked |
| AGT-04 | DevOps writer agent with runbook structure, copy-paste-ready commands | Same agent pattern; runbook conventions locked |
| AGT-05 | Glossary writer agent for terminology reconciliation across audiences | Specialized role: receives term proposals, writes definitions, updates GLOSSARY.md |
| AGT-06 | Staleness scanner agent for per-section freshness analysis | Integrates with Phase 3 scan pipeline; uses staleness-check.py and check-references.py |
| AGT-07 | Verifier agent for cross-reference, Diataxis, and completeness checking | Integrates with Phase 5 verify pipeline; uses check-references.py |
| AGT-08 | Writer agents run in parallel (one per audience + glossary) | Execution order documented in CONTEXT.md cross-cutting decisions; parallel execution instructions go in TEMPLATE.md and generate command |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Markdown (.md) | N/A | Template and agent definition file format | Project convention; all mg-cc-tools agents and commands are .md files |
| HTML comments | N/A | Purpose statements and exemplars in templates | Locked decision; comments stripped from final output |
| YAML frontmatter | N/A | Agent doc metadata (scope, last_generated, sources) | Locked for agent-audience docs; follows Codified Context paper |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Diataxis framework | N/A | Classification system for doc types | Each template tagged with its Diataxis type |
| Style guide | references/style-guide.md | Cross-audience writing conventions | Writer agents reference at generation time |
| Schema | references/schema.md | docs-scan.json data contract | Agents reference for understanding scan output |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| HTML comments for purpose/exemplar | YAML frontmatter sections | HTML comments are locked decision; they're invisible in rendered output |
| Individual agent files | Single combined agent file | Individual files follow codebase-health pattern; better context isolation |

**No installation step for Phase 2** -- all deliverables are static .md files. The install.sh patch is the only "code" change.

## Architecture Patterns

### Recommended Project Structure

```
create-docs/
├── agents/
│   ├── TEMPLATE.md                 <- Shared writer agent pattern (NEW)
│   ├── end-user-writer.md          <- AGT-01 (NEW)
│   ├── developer-writer.md         <- AGT-02 (NEW)
│   ├── agent-writer.md             <- AGT-03 (NEW)
│   ├── devops-writer.md            <- AGT-04 (NEW)
│   ├── glossary-writer.md          <- AGT-05 (NEW)
│   ├── staleness-scanner.md        <- AGT-06 (NEW)
│   └── verifier.md                 <- AGT-07 (NEW)
└── references/
    └── templates/
        ├── OVERVIEW.template.md        <- Shared (NEW)
        ├── GLOSSARY.template.md        <- Shared (NEW)
        ├── end-users/
        │   ├── USER_GUIDE.template.md      <- (NEW)
        │   └── DOMAIN_SPECIFIC.template.md <- (NEW)
        ├── developers/
        │   ├── ARCHITECTURE.template.md        <- (NEW)
        │   ├── DEVELOPER_GUIDE.template.md     <- (NEW)
        │   └── QUICK_REFERENCE.template.md     <- (NEW)
        ├── agents/
        │   ├── SYSTEM_MAP.template.md      <- (NEW)
        │   ├── CONVENTIONS.template.md     <- (NEW)
        │   ├── GOTCHAS.template.md         <- (NEW)
        │   └── TESTING.template.md         <- (NEW)
        └── devops/
            ├── OPERATIONS.template.md      <- (NEW)
            └── TROUBLESHOOTING.template.md <- (NEW)
```

Total new files: 8 agent files + 13 template files + install.sh patch = 22 deliverables.

### Pattern 1: Three-Layer Template Format

**What:** Every template file follows a consistent three-layer structure with HTML comments.
**When to use:** All 13 template files.

```markdown
<!-- DIATAXIS: how-to -->
<!-- AUDIENCE: end-users -->

# {Document Title}

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Section Name
<!-- PURPOSE: 1-2 sentences explaining why this section exists and what
     the reader needs from it. Guides the writer agent on what to generate. -->
<!-- EXAMPLE:
A concrete example showing what this section looks like when filled in
for a real project. This is the exemplar -- the most impactful element
for LLM generation quality.

| Column 1 | Column 2 |
|----------|----------|
| Example  | Data     |
-->

## Another Section
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Why this section might exist for some projects but not others. -->
<!-- EXAMPLE:
What this section looks like when it IS applicable.
-->
```

**Key rules:**
- Layer 1 (classification) goes at the very top as HTML comments
- Layer 2 (structure) is the section heading + PURPOSE comment
- Layer 3 (exemplar) is the EXAMPLE comment with concrete content
- OPTIONAL marker goes before PURPOSE when applicable
- docs-meta comment goes after the title for future staleness tracking
- No placeholder text between sections -- the comments ARE the template content

### Pattern 2: Writer Agent Definition (follows codebase-health pattern)

**What:** Each writer agent .md file follows the structure from `codebase-health/agents/TEMPLATE.md` but adapted for documentation writing rather than code scanning.
**When to use:** All 4 writer agents and glossary agent.

```markdown
# {Audience} Writer Agent

{Brief 1-2 sentence description of this agent's role and audience.}

## Role

You are a specialized writer agent for the **{audience}** audience. You generate
documentation sections using templates, source material, and the style guide.
**You write documentation files in the project's docs directory.**

## Inputs

- **project_root**: Path to the project.
- **docs_dir**: Path to the documentation output directory (from config).
- **scan_data_path**: Path to `docs-scan.json` (read for source material index).
- **templates_dir**: Path to `{TEMPLATES_DIR}/{audience}/`.
- **style_guide_path**: Path to `references/style-guide.md`.
- **glossary_path**: Path to the current GLOSSARY.md (for terminology consistency).
- **documents**: List of document names to generate (from config).
- **mode**: `"initial"` or `"update"`.

## Process

1. **Read inputs** -- Load scan data, style guide, glossary.
2. **For each assigned document:**
   a. Read the template from templates_dir
   b. For each section in the template:
      - Read the PURPOSE comment (understand what to generate)
      - Read the EXAMPLE comment (understand what "good" looks like)
      - Look up source material in scan_data for this section
      - Generate section content following style guide conventions
      - Include docs-meta comment with sources and timestamp
      - If section is OPTIONAL and no relevant source material: skip it
   c. Write the complete document
3. **Propose terms** -- For any new terms used, output a term proposal list.

## {Audience}-Specific Conventions

{The locked format conventions from CONTEXT.md for this audience}

## Principles

- Follow the style guide for all formatting decisions.
- Use glossary terms consistently -- check before using synonyms.
- Source material over inference -- generate from what the scan found, not guesses.
- Skip optional sections rather than generate empty boilerplate.
- Include docs-meta comments for future staleness tracking.
```

### Pattern 3: Specialized Agent Definition (staleness/verifier)

**What:** Non-writer agents that perform analysis rather than generation.
**When to use:** staleness-scanner.md and verifier.md.

These follow the same basic structure (Role, Inputs, Process, Principles) but their Process section describes analytical operations rather than writing operations. They reference Python scripts (`check-references.py`, `staleness-check.py`) for deterministic checks.

### Anti-Patterns to Avoid

- **Template without exemplar:** Headings-only templates produce generic LLM output. The EXAMPLE comment is the single most impactful element (Tom Johnson research). Every non-optional section MUST have an exemplar.
- **Mixed Diataxis types:** A template classified as "how-to" must not contain reference-style API listings or explanation-style design discussions. Each template is ONE Diataxis type (or explicitly declares its mixed nature like DEVELOPER_GUIDE which is "How-to + Tutorial").
- **Agent that pastes templates into prompt:** The CONTEXT.md explicitly says agents receive file paths and read files themselves. Do NOT design agents that expect templates pasted into their Task prompt.
- **Word counts in templates:** Locked decision -- no word count constraints. They produce padding or truncation.
- **Glossary agent running in parallel with writers:** Cross-cutting decision clarified that glossary runs FIRST (initial pass), then writers in parallel, then glossary reconciliation, then OVERVIEW last.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Template format validation | Custom validation script | Manual review during plan verification | Templates are static content; their quality is validated by reading them, not by scripts |
| Agent prompt structure | Novel prompt engineering | codebase-health agent pattern (TEMPLATE.md + specialized agents) | Established pattern in this codebase; consistency matters more than novelty |
| Diataxis classification | Custom classification logic | HTML comment tags at template top | Classification is metadata, not runtime logic |
| Style guide integration | Inline style rules per agent | Reference to existing style-guide.md via file path | Style guide already exists from Phase 1; agents read it at runtime |

**Key insight:** Phase 2 produces content files, not code. The "don't hand-roll" principle here means: don't invent new patterns when existing codebase patterns (from codebase-health) already work. Follow the established agent template pattern.

## Common Pitfalls

### Pitfall 1: Shallow Exemplars
**What goes wrong:** Template exemplars that are too abstract or short to be useful. A PURPOSE says "describe the architecture" and the EXAMPLE just says "The system uses a client-server architecture."
**Why it happens:** Writing good exemplars for 13 templates is tedious creative work. It's tempting to write something perfunctory.
**How to avoid:** Each exemplar should contain 3-10 lines of concrete content showing exactly what a filled-in section looks like for a realistic project. Use tables, code blocks, and specific names -- not generic placeholders.
**Warning signs:** Exemplars shorter than 3 lines, or exemplars that use placeholder names like "Component A" instead of realistic names like "Scoring Engine."

### Pitfall 2: install.sh Templates Directory Gap
**What goes wrong:** Templates are authored but never copied by install.sh. The tool installs but agents can't find templates at runtime.
**Why it happens:** Phase 1's install.sh copies individual reference files but has no recursive copy for `references/templates/`. The `{TEMPLATES_DIR}` placeholder resolves correctly, but the directory it points to is empty after install.
**How to avoid:** Add a recursive copy of `references/templates/` to install.sh as part of this phase. Must handle subdirectory structure (end-users/, developers/, agents/, devops/).
**Warning signs:** `ls $SUPPORT_DIR/references/templates/` returns empty after install.

### Pitfall 3: Agent Prompt Too Long
**What goes wrong:** Agent .md files exceed what can be practically pasted into a Task tool prompt alongside the subagent's working context.
**Why it happens:** Including too much detail in the agent definition instead of referencing external files (style guide, templates) by path.
**How to avoid:** Agent definitions should focus on: role, inputs, process steps, audience-specific conventions, principles. The style guide, schema, and templates are referenced by path -- the agent reads them at runtime. Target: agent definitions under 200 lines each.
**Warning signs:** Agent .md files exceeding 300 lines.

### Pitfall 4: Inconsistent Template Structure
**What goes wrong:** Templates for different documents follow slightly different comment formats, making it harder for writer agents to parse them consistently.
**Why it happens:** Templates are authored as separate plans/tasks and small variations creep in.
**How to avoid:** Establish the exact comment format in the first template authored, then use it as a reference for all subsequent templates. The format is:
- `<!-- DIATAXIS: type -->` (top of file)
- `<!-- AUDIENCE: audience-name -->` (top of file)
- `<!-- PURPOSE: ... -->` (per section)
- `<!-- EXAMPLE: ... -->` (per section)
- `<!-- OPTIONAL -- delete if not applicable -->` (before PURPOSE when applicable)

### Pitfall 5: Forgetting the CONTEXT.md Execution Order Conflict
**What goes wrong:** Agent definitions describe glossary running in parallel with writers, contradicting the cross-cutting decision.
**Why it happens:** CONTEXT.md itself notes the conflict between AGT-08 ("writer agents in parallel: one per audience plus glossary") and the cross-cutting decision ("glossary first, then 4 writers in parallel, then glossary reconciliation, then OVERVIEW last").
**How to avoid:** The cross-cutting decision takes precedence. The TEMPLATE.md and agent definitions should encode the sequential-then-parallel order: (1) glossary initial pass, (2) 4 writers in parallel, (3) glossary reconciliation, (4) OVERVIEW.md generation.

## Code Examples

### Template File Example: OPERATIONS.template.md

```markdown
<!-- DIATAXIS: how-to + reference -->
<!-- AUDIENCE: devops -->

# Operations Guide

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Infrastructure Overview
<!-- PURPOSE: Operators need a single-page mental model of the system's
     deployment topology. What runs where, how components connect, and
     what external dependencies exist. This is the first thing to check
     during an incident. -->
<!-- EXAMPLE:
### Deployment Topology

| Component | Host | Port | Health Check |
|-----------|------|------|-------------|
| API Server | app-01.internal | 8080 | GET /health |
| Worker Pool | worker-01.internal | -- | Prefect agent heartbeat |
| PostgreSQL | db-01.internal | 5432 | pg_isready |

### External Dependencies

| Service | Purpose | Timeout | Fallback |
|---------|---------|---------|----------|
| OpenAI API | LLM scoring | 30s | Cached results from last successful run |
| S3 (data lake) | Input file storage | 10s | Local file fallback |
-->

## Deployment
<!-- PURPOSE: Step-by-step deployment procedure that an operator can follow
     at 3am without prior context. Every command must be copy-paste-ready.
     Must include both deploy and rollback. -->
<!-- EXAMPLE:
### Deploy

**Prerequisites:**
- [ ] SSH access to app-01.internal
- [ ] Latest `.env.production` values confirmed
- [ ] Database migrations applied (check `alembic heads`)

1. Pull latest code:
   ```bash
   ssh app-01.internal
   cd /opt/app && git pull origin main
   ```
2. Rebuild containers:
   ```bash
   docker compose build --no-cache api worker
   ```
3. Deploy with zero-downtime restart:
   ```bash
   docker compose up -d --remove-orphans
   ```
4. Verify:
   ```bash
   curl -s http://localhost:8080/health | jq .status
   # Expected: "ok"
   ```

### Rollback

1. Check previous image tag:
   ```bash
   docker compose logs api | head -1
   # Note the image hash
   ```
2. Revert to previous commit:
   ```bash
   git checkout HEAD~1
   docker compose up -d --build
   ```
-->

## Service Management
<!-- PURPOSE: How to start, stop, restart individual services. Operators
     need this during maintenance windows and partial outages. -->
<!-- EXAMPLE:
| Action | Command | Expected Output |
|--------|---------|-----------------|
| Start all | `docker compose up -d` | All containers running |
| Stop all | `docker compose down` | All containers stopped |
| Restart API only | `docker compose restart api` | API container restarted |
| View logs | `docker compose logs -f --tail=100 api` | Streaming logs |
| Check status | `docker compose ps` | Container status table |
-->

## Configuration Reference
<!-- PURPOSE: Complete reference of all configuration knobs. Operators
     need to know what can be changed, where to change it, and what
     effect it has. -->
<!-- EXAMPLE:
### Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | -- | Yes | PostgreSQL connection string |
| `OPENAI_API_KEY` | -- | Yes | API key for LLM scoring |
| `LOG_LEVEL` | `INFO` | No | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `WORKER_CONCURRENCY` | `4` | No | Number of parallel worker threads |

### Configuration Files

| File | Purpose | Restart Required |
|------|---------|-----------------|
| `.env` | Environment variables | Yes |
| `config.yaml` | Application settings | Yes (hot reload planned for v2) |
-->

## Monitoring & Alerting
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: What to monitor, where alerts are configured, and how to
     respond to common alerts. Only applicable for projects with
     monitoring infrastructure. -->
<!-- EXAMPLE:
### Key Metrics

| Metric | Alert Threshold | Response |
|--------|----------------|----------|
| API response time (p95) | > 2s for 5min | Check database query performance |
| Worker queue depth | > 100 pending | Scale worker pool or investigate stuck jobs |
| Disk usage | > 85% | Rotate logs, clean temp files |
-->
```

### Agent Definition Example: Writer Agent Shared Template (TEMPLATE.md)

```markdown
# Writer Agent Template

This template documents the common execution pattern shared by all writer
agents. Each agent has its own file with audience-specific conventions,
but they all follow this structure for inputs, outputs, and process.

The following writer agent files exist:
- `agents/end-user-writer.md`
- `agents/developer-writer.md`
- `agents/agent-writer.md`
- `agents/devops-writer.md`

## Role

You are a specialized writer agent for the **[AUDIENCE_NAME]** audience.
You generate documentation by reading templates and source material,
then writing document files to the project's docs directory.

## Inputs

- **project_root**: Path to the project.
- **docs_dir**: Absolute path to the output docs directory.
- **scan_data_path**: Path to `.mg/docs/docs-scan.json`.
- **templates_dir**: Path to the audience's template directory.
- **style_guide_path**: Path to `references/style-guide.md`.
- **glossary_path**: Path to the current GLOSSARY.md (for terminology).
- **documents**: List of document names this agent is responsible for.
- **mode**: `"initial"` or `"update"`.
- **update_sections**: (Update mode only) List of sections approved for update.

## Process

1. **Read context** -- Load the scan data JSON, style guide, and glossary.
2. **For each assigned document:**
   a. Read the template file from templates_dir.
   b. Extract sections: parse `## ` headings and their associated
      PURPOSE and EXAMPLE comments.
   c. For each section:
      - Read the PURPOSE comment to understand what to generate.
      - Read the EXAMPLE comment to understand what "good" looks like.
      - Look up source material: find the matching entry in
        `scan_data.source_material_index` for this document/section.
      - Read the actual source files listed in the index.
      - In update mode: skip sections not in `update_sections`.
      - If section is marked OPTIONAL and no relevant source material
        exists: skip this section entirely.
      - Generate section content following:
        * The PURPOSE guidance for what to cover
        * The EXAMPLE for format and depth
        * The style guide for writing conventions
        * The glossary for terminology
      - Add a `docs-meta` comment after each section heading.
   d. Write the complete document to docs_dir.
3. **Propose new terms** -- Output a JSON array of term proposals:
   ```json
   [{"term": "scoring engine", "context": "Component that evaluates stocks"}]
   ```
   Write proposals to `.mg/docs/scan-logs/terms-{audience}.json`.

## Output Conventions

- Write files to `{docs_dir}/{audience}/` for audience-specific docs.
- Write shared docs to `{docs_dir}/` root.
- Use the document name from config as the filename (e.g., `ARCHITECTURE.md`).
- Include `docs-meta` HTML comments for staleness tracking.
- Strip template comments (PURPOSE, EXAMPLE, OPTIONAL) from output.

## Principles

- Source material over inference. Generate from what the scan found.
- Follow the style guide. It defines voice, formatting, and conventions.
- Use glossary terms consistently. Never introduce synonyms.
- Skip optional sections rather than generating empty boilerplate.
- One Diataxis type per document. Check the DIATAXIS comment in the template.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat templates (headings only) | Three-layer templates (classification + structure + exemplar) | Good Docs Project + Tom Johnson 2024 | Purpose statements + examples dramatically improve LLM output quality |
| JSON/YAML for agent docs | Markdown with YAML frontmatter | 2024-2025 industry convergence | 15-16% more token efficient; AGENTS.md pattern standard across Claude/Cursor/Copilot |
| Single monolithic doc | Audience-segmented docs | Diataxis + Codified Context 2025 | Different audiences need fundamentally different content, format, depth |

**Deprecated/outdated:**
- Single README.md as documentation: inadequate for multi-audience needs
- JSON Schema for agent context: reasoning penalty per arXiv 2408.02442

## Open Questions

1. **Templates directory copy in install.sh**
   - What we know: install.sh has `TEMPLATES_ABS` defined and `{TEMPLATES_DIR}` sed resolution, but NO recursive copy of `references/templates/` directory tree
   - What's unclear: Should the copy preserve subdirectory structure (end-users/, developers/, etc.) or flatten?
   - Recommendation: Add recursive copy preserving subdirectory structure. Use `cp -r "${SCRIPT_DIR}/references/templates" "${SUPPORT_DIR}/references/"`. This is a small patch to install.sh.

2. **DOMAIN_SPECIFIC.template.md scope**
   - What we know: This is a meta-template for project-defined custom documents. The config allows `custom_documents` with name, audience, and description.
   - What's unclear: How detailed should this template be since the actual document type varies per project?
   - Recommendation: Make it a generic "project-specific reference" template with configurable sections. Keep it simpler than audience-specific templates since it's inherently generic.

3. **Agent definition size budget**
   - What we know: codebase-health agents (orphaned-code.md, sprawling-code.md) are 100-150 lines. The scan command reads agent files and pastes contents into Task prompts.
   - What's unclear: The CONTEXT.md says "agents receive file paths only, read files themselves." This contradicts the codebase-health pattern where agents are pasted into prompts.
   - Recommendation: Design agents to work BOTH ways -- keep them self-contained enough to be pasted (under 200 lines) but also reference external files by path. The generate command (Phase 4) will determine the final spawning mechanism. Agent definitions should be written so they work regardless.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml |
| Quick run command | `python3 -m pytest create-docs/scripts/tests/ -x` |
| Full suite command | `python3 -m pytest` |

### Phase Requirements to Test Map

Phase 2 is primarily a content authoring phase. Most requirements are verified by file existence and content inspection, not automated tests.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TPL-01 | Three-layer template architecture in every template | manual-only | Grep for PURPOSE and EXAMPLE comments in all templates | Wave 0 |
| TPL-02 | 13 templates exist in correct directory structure | smoke | `test -f create-docs/references/templates/OVERVIEW.template.md && ...` | Wave 0 |
| TPL-03 | Optional sections marked with OPTIONAL comment | manual-only | Grep for `<!-- OPTIONAL` in templates that have optional sections | Wave 0 |
| AGT-01 | End-user writer agent with format conventions | manual-only | Read file, verify conventions present | Wave 0 |
| AGT-02 | Developer writer agent with code-first conventions | manual-only | Read file, verify conventions present | Wave 0 |
| AGT-03 | Agent writer agent with YAML frontmatter instructions | manual-only | Read file, verify conventions present | Wave 0 |
| AGT-04 | DevOps writer agent with runbook conventions | manual-only | Read file, verify conventions present | Wave 0 |
| AGT-05 | Glossary writer agent | manual-only | Read file, verify reconciliation instructions | Wave 0 |
| AGT-06 | Staleness scanner agent | manual-only | Read file, verify integration with staleness-check.py | Wave 0 |
| AGT-07 | Verifier agent | manual-only | Read file, verify integration with check-references.py | Wave 0 |
| AGT-08 | Parallel execution instructions | manual-only | Verify execution order in TEMPLATE.md and relevant agents | Wave 0 |

### Sampling Rate
- **Per task commit:** Verify files exist and contain expected comment patterns
- **Per wave merge:** `python3 -m pytest` (ensure no regressions from install.sh changes)
- **Phase gate:** All 21 new files exist + install.sh copies templates + full suite green

### Wave 0 Gaps
- No new test files needed -- Phase 2 deliverables are content files verified by reading
- install.sh patch needs existing test suite to still pass: `python3 -m pytest`
- File existence verification via bash: check all 13 templates and 8 agent files exist

## Sources

### Primary (HIGH confidence)
- Codebase-health agent pattern files read directly: `codebase-health/agents/TEMPLATE.md`, `orphaned-code.md`, `sprawling-code.md`
- Codebase-health scan command read directly: `codebase-health/commands/codebase-health-scan.md`
- Phase 1 deliverables read directly: `create-docs/references/style-guide.md`, `create-docs/references/schema.md`, `create-docs/install.sh`
- CONTEXT.md locked decisions read directly
- DESIGN.md full specification read directly: `docs/work-queue/todo/doc-command/DESIGN.md`
- Phase 2 detailed spec read directly: `docs/work-queue/todo/doc-command/phase-docs/phase-02-templates-agent-definitions.md`

### Secondary (MEDIUM confidence)
- [Diataxis framework official site](https://diataxis.fr) -- verified tutorial, how-to, reference, explanation principles
- [The Good Docs Project](https://www.thegooddocsproject.dev/template) -- 26 templates with purpose statements, examples, and guidance; confirms the three-layer approach

### Tertiary (LOW confidence)
- Tom Johnson "I'd Rather Be Writing" research findings -- referenced in DESIGN.md but not independently verified (research is from the user's prior analysis)
- arXiv papers (2602.20478, 2601.20404, 2408.02442) -- cited in DESIGN.md, not independently fetched

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all decisions locked in CONTEXT.md; patterns verified from existing codebase
- Architecture: HIGH - directory structure, file format, and agent pattern all defined by locked decisions and existing codebase-health exemplars
- Pitfalls: HIGH - identified from direct codebase analysis (install.sh gap, codebase-health agent patterns, CONTEXT.md conflict resolution)

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable -- content authoring, no external dependencies)
