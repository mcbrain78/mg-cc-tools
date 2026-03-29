# `/mg:docs` — Documentation Lifecycle Tool

## Purpose

A documentation tool that scans a project and generates/maintains audience-segmented documentation. It integrates with the GSD milestone lifecycle so documentation stays current as the project evolves, and provides a lightweight note-capture command for recording operational knowledge during development.

## Problem Statement

Documentation is manually created (see `ai-stock-ranker/docs/documentation_v3/` for an example of what the user produces by hand). This is time-consuming, falls out of date as code changes, and lacks systematic coverage across audiences. Different consumers of documentation (end users, developers, AI agents, operations staff) need fundamentally different content, formats, and depth levels — but maintaining 4 parallel documentation sets manually is impractical.

## Commands

| Command | Purpose | Pipeline Step |
|---|---|---|
| `/mg:create-docs` | Full pipeline: scan → generate → verify. Entry point that detects state and routes. | All |
| `/mg:create-docs-scan` | Analyze project, build source material index, detect staleness | Step 1 (read-only) |
| `/mg:create-docs-generate` | Create or update documents section-by-section | Step 2 (writes docs) |
| `/mg:create-docs-verify` | Cross-reference check, Diataxis mixing detection, completeness audit | Step 3 (read-only) |
| `/mg:add-docs "note"` | Capture a note to the inbox with auto-classification | Standalone (writes inbox only) |

The main entry point `/mg:create-docs` detects existing state (no docs = initial creation, existing docs = update mode, existing scan = resume) and routes to the appropriate step — same pattern as `/mg:codebase-health`.

---

## Audiences & Document Types

### 4 Audience Subdirectories

Each audience gets its own subdirectory under `docs/auto-doc/` with a self-contained set of documents. Two shared documents (`OVERVIEW.md`, `GLOSSARY.md`) sit at the root to avoid redundancy.

### End Users (`end-users/`)

**Who:** Non-technical users of the system (portfolio managers, business analysts, internal platform users).

**What they need:** Task-oriented guides in plain language. How to accomplish specific goals without understanding internals.

**Documents:**

| Document | Diataxis Type | Content |
|---|---|---|
| `USER_GUIDE.md` | How-to | Task-oriented articles: "How do I export my portfolio?", "How do I configure a new analysis run?" Numbered steps, max 7 per procedure, one action per step. |
| `[domain-specific].md` | Reference | Project-specific specs that end users need. Examples: `EXCEL_FORMAT.md` (input file specification), `API_USAGE.md` (if the system exposes a user-facing API). Defined in project config. |

**Format conventions** (backed by NNGroup research):
- Plain language, no jargon. Active voice: "Click Save" not "The Save button can be clicked"
- Scannable formatting: headings, bullet lists, tables. Scanning-optimized formatting improves usability by 58%
- Numbered steps with one action per step, max 7 steps per procedure (Microsoft research)
- Tables for comparing options, showing settings, summarizing parameters
- Progressive disclosure: most important information first, details via subsections
- Task-oriented structure: organize by user goal ("How do I..."), not by system module

### Human Developers (`developers/`)

**Who:** Software engineers who maintain and extend the codebase.

**What they need:** Architecture understanding, code examples, fast lookups. Stripe/Twilio-style docs where code examples are primary and prose supports them.

**Documents:**

| Document | Diataxis Type | Content |
|---|---|---|
| `ARCHITECTURE.md` | Explanation | System design, data model, component interactions, database schema, orchestration patterns, architectural decision records (ADRs). Uses arc42-inspired structure. |
| `DEVELOPER_GUIDE.md` | How-to + Tutorial | Code examples for common tasks, extension patterns, testing approaches. Organized by developer goal ("I want to add a new archetype"), not by internal module. |
| `QUICK_REFERENCE.md` | Reference | Cheat sheet: key file paths, database tables, common commands, lookup tables. Pure tables, no prose. Designed for fast scanning and copy-paste. |

**Format conventions** (backed by SmartBear surveys, Stripe/Diataxis research):
- Code examples are #1 priority — interleave prose and code, never large blocks of either alone
- Organize by developer goal, not internal API structure
- Separate tutorials from reference from explanation — never mix Diataxis types
- Fenced code blocks with language tags
- Copy-paste-ready commands and examples
- "I want to..." lookup tables for common tasks

### AI Agents (`agents/`)

**Who:** AI coding assistants (Claude Code, Copilot, Cursor, etc.) that need to understand and work with the codebase.

**What they need:** Structured, explicit, machine-optimized documentation. No vague pronouns, exact file paths and symbol names. Follows the "Codified Context" three-tier architecture (arXiv:2602.20478).

**Documents:**

| Document | Diataxis Type | Content |
|---|---|---|
| `SYSTEM_MAP.md` | Reference | Component registry: name, purpose, file paths, dependencies, public API surface per component. Data flow description. Configuration effects table (config key → behavioral change). |
| `CONVENTIONS.md` | Reference | Code patterns the codebase follows, naming conventions, architectural patterns, explicit "do this / don't do this" rules. |
| `GOTCHAS.md` | Reference | Edge cases, ordering constraints, invariants, things an agent would get wrong. "Flows should only be called once during tests" type knowledge. |
| `TESTING.md` | How-to | Test isolation requirements, fixture patterns, what to mock vs not, test markers/categories. |

**Format conventions** (backed by Codified Context paper, AGENTS.md research):
- All files are Markdown with YAML frontmatter (for metadata: scope, last_generated, sources)
- Explicit over implicit: replace vague pronouns with exact names. "Save `config.yaml` and restart the server" not "save it and restart"
- Consistent terminology: one term per concept, used identically everywhere
- Tables for structured data (config options, API surfaces, error conditions)
- Fenced code blocks with language tags
- Unique heading names (avoids vector embedding overlap)
- Separate sections for distinct topics (prevents semantic chunking problems)
- YAML frontmatter provides machine-parseable metadata for filtering and progressive context loading

**Why Markdown and not JSON/YAML for agent docs:**
- Every major AI coding tool uses Markdown (CLAUDE.md, AGENTS.md, .cursor/rules) — industry convergence
- Markdown is 15-16% more token-efficient than pretty-printed JSON (OpenAI community analysis)
- YAML uses 6-10% MORE tokens than compact JSON, contrary to popular belief (tiktoken analysis across 6 models)
- Forcing structured output (JSON-mode) degrades LLM reasoning by 10-15% ("Let Me Speak Freely", arXiv 2408.02442)
- AGENTS.md presence correlates with 28.64% reduction in median agent runtime (arXiv 2601.20404)
- YAML frontmatter gives machine-parseable metadata; Markdown body gives rich documentation

### DevOps (`devops/`)

**Who:** People who deploy, monitor, and troubleshoot the system in production.

**What they need:** Runbook-structured procedures with exact commands. Decision trees over prose. Copy-paste-ready at 3am during an incident.

**Documents:**

| Document | Diataxis Type | Content |
|---|---|---|
| `OPERATIONS.md` | How-to + Reference | Infrastructure details (hosts, ports, access), deployment procedures, rollback procedures, service management (start/stop/restart), configuration reference (env vars, secrets, config files), monitoring & alerting. |
| `TROUBLESHOOTING.md` | How-to | Structured as symptom → cause → fix entries. Escalation paths. Common failure modes. Each entry is a mini-runbook. |

**Format conventions** (backed by PagerDuty, Google SRE, AWS Well-Architected):
- Runbook structure: alert/trigger → severity → pre-checks → numbered steps → verification → escalation
- Concrete commands with full syntax — never "restart the service" without the exact command
- Decision trees and checklists over prose paragraphs
- Every deployment procedure includes a matching rollback procedure
- Copy-paste-ready: every command tested and exact
- Service architecture diagrams as ASCII text (LLMs can't process images)

### Shared Documents (root of `docs/auto-doc/`)

| Document | Diataxis Type | Content |
|---|---|---|
| `OVERVIEW.md` | Explanation | Business purpose, system-level architecture summary (1-2 paragraphs, not the deep dive), key concepts, audience routing ("developers: see developers/ARCHITECTURE.md"). The "landing page" that avoids repeating context across subdirs. |
| `GLOSSARY.md` | Reference | Complete term definitions organized by category (system concepts, domain terms, technical terms). Source of truth for terminology — all writer agents must use glossary terms consistently. |

---

## Three-Layer Template Architecture

Research converges on a sweet spot for LLM-generated documentation (Good Docs Project + Tom Johnson + Diataxis framework):

### Layer 1: Classification

Each document is tagged with its Diataxis type (tutorial, how-to, reference, explanation). This tells the writer agent what principles to follow:
- **Tutorial**: Sequential narrative, concrete actions producing visible outcomes, minimal explanation
- **How-to**: Recipe model — prerequisites + numbered steps, action-only, no digression
- **Reference**: Mirror the product structure, adopt consistent patterns across entries
- **Explanation**: Thematic, connections, alternatives, opinions, bounded by topic

### Layer 2: Structural

Section headings with a **purpose statement** per section (1-2 sentences explaining *why* this section exists). This is the critical differentiator between mediocre and good LLM output — the "why" lets the LLM adapt the skeleton intelligently rather than filling in generic content.

Optional sections are explicitly marked `<!-- OPTIONAL — delete if not applicable -->`.

### Layer 3: Exemplar

One concrete example per section showing what "good" looks like. Research (Tom Johnson) shows this is the single most impactful element for LLM-generated documentation quality.

### Template File Format

Templates live in `references/templates/` organized by audience. Each template is a Markdown file with HTML comments containing purpose statements and examples. The comments are stripped from the final output.

```markdown
## Section Name
<!-- PURPOSE: 1-2 sentences explaining why this section exists and what
     an operator/developer/user needs from it. -->
<!-- EXAMPLE:
A concrete example showing what this section looks like when filled in
for a real project. Tables, code blocks, etc. as they would appear.
-->
```

### Why This Depth

- Section headings alone (no purpose/examples) produce generic, low-quality LLM output (TGDP finding)
- Purpose statements + examples together let the LLM adapt the template to the specific project (Tom Johnson's key finding)
- Marking optional sections prevents empty boilerplate (every source warns about this)
- Word counts and length constraints are explicitly avoided — they produce padding or truncation

---

## Pipeline

### Step 1: Scan (read-only)

**Orientation** — Build understanding of the project:
- Code structure, tech stack, frameworks, entry points
- Deployment artifacts (Dockerfile, docker-compose, systemd units, CI/CD pipelines)
- Existing documentation (docs/, README, CLAUDE.md, inline comments)
- Database schemas, API contracts, configuration files
- Environment files (.env.example, config templates)

**Source Material Index** — Map which code files are relevant to which document and section. This is critical because research shows generating documentation without feeding source material produces hallucinations. The index structure:

```json
{
  "documents": {
    "devops/OPERATIONS.md": {
      "sections": {
        "Infrastructure": {
          "sources": ["deploy/docker-compose.yml", "deploy/config.yml", ".env.example"],
          "staleness": null
        },
        "Deployment": {
          "sources": ["Makefile", "scripts/deploy.sh", ".github/workflows/deploy.yml"],
          "staleness": null
        }
      }
    }
  }
}
```

**GSD Context** (if `.planning/` exists):
- Read all phase SUMMARY.md files from the current/latest milestone to understand what changed
- Read REQUIREMENTS.md traceability table for feature coverage
- Read VERIFICATION.md files for known gaps
- Read MILESTONES.md for historical context
- These drive targeted updates rather than full rewrites in update mode

**Staleness Detection** (if docs already exist):
- **Code-reference check**: Do file paths, function names, class names mentioned in docs still exist? (Python script `check-references.py`)
- **Git-based freshness**: Which code files referenced by a doc section changed since that section was last touched? (Python script `staleness-check.py`)
- **Schema drift**: Compare documented DB schemas, API contracts against actual source
- **Terminology drift**: Do glossary terms match actual usage in code and docs?
- **GSD deviation signals**: Phase SUMMARYs listing deviations and new decisions flag sections that likely need updates

**Notes Inbox Processing** — Classify each pending note from `.mg/docs/notes-inbox.json`:
- Target audience, document, and section
- Confidence level of the classification
- Proposed expansion outline

**Output**: `.mg/docs/docs-scan.json` — the shared data contract containing:
- Project model (components, APIs, infrastructure discovered)
- Source material index (code file → document → section mapping)
- Per-section staleness report (if docs exist)
- Note classifications (from inbox)
- Gap analysis (what exists in code but isn't documented for each audience)

### Step 2: Generate/Update (writes docs, with approval gate)

**Initial Mode** (no existing docs):
For each document, generate section-by-section following the three-layer template. For each section:
1. Read the template (heading + purpose + example)
2. Read the source material mapped to this section from the scan
3. Generate the section content
4. Move to next section

Writer agents run in parallel — one per audience (4 total) plus a glossary agent.

**Update Mode** (docs exist):
1. Present staleness report to user: which sections are stale, what changed, draft suggested update
2. Present classified inbox notes: where each note would go, how it would be expanded
3. User approves which updates to apply
4. Generate only approved sections, feeding source material per section
5. Integrate approved inbox notes into their target locations

**Writer Agent Inputs:**
- The audience-specific templates for their documents
- The source material index entries from the scan
- The current doc content (if exists, for update mode)
- The glossary (for terminology consistency)
- The style guide (cross-audience writing conventions)

**Section Ownership Tracking:**
Each generated section includes an HTML comment marker for future staleness detection:
```html
<!-- docs-meta: last-updated: 2026-03-15, sources: [src/flows/scoring.py, src/models/config.py] -->
```
This tells future scans which code files drive this section and when it was last generated.

**Cross-Document Consistency:**
- Writer agents receive the glossary as input
- New terms discovered during writing are proposed for glossary addition
- The glossary agent reconciles all proposals and updates GLOSSARY.md
- OVERVIEW.md is generated last, after all subdirs are complete, so it can accurately route audiences

### Step 3: Verify (read-only, with approval gate)

Checks the generated/updated documentation for quality issues:

- **Reference integrity**: Every file path, symbol, command mentioned in docs → verify it exists in the codebase (`check-references.py`)
- **Cross-doc consistency**: Terms used match glossary, architecture descriptions match developer guide descriptions of the same components
- **Diataxis mixing**: Flag sections where tutorial content creeps into reference docs, or explanation gets buried in how-to guides (the #1 documentation anti-pattern per Diataxis)
- **Completeness**: Major code components have at least basic documentation for each relevant audience
- **Example validity**: Code examples are syntactically valid
- **Link integrity**: Internal markdown links between docs resolve
- **Agent doc quality**: YAML frontmatter is valid, file paths in SYSTEM_MAP.md exist, convention rules reference real patterns

**Output**: `.mg/docs/docs-verify-report.md` with issues categorized by severity. User reviews and can trigger re-generation for flagged sections.

---

## `/mg:add-docs` — Notes Inbox

### Use Case

During development, you notice something important to document:
```
/mg:add-docs "Production server is at 10.0.1.50, SSH via bastion.example.com on port 2222"
/mg:add-docs "Flows should only be called once during tests — calling twice causes duplicate DB entries"
/mg:add-docs "Use the .env.staging keys when testing against the staging API, never .env.production"
```

### Behavior

1. Note stored in `.mg/docs/notes-inbox.json` with:
   - Unique ID (`NOTE-001`, `NOTE-002`, ...)
   - Raw text from the user
   - Timestamp
   - Context: active file (if detectable), GSD phase (if applicable)
2. Auto-classified: audience → document → section, with confidence level
3. User sees the classification immediately and can correct it
4. Note stays in inbox until `/mg:create-docs` processes it

### Inbox Schema

```json
{
  "notes": [
    {
      "id": "NOTE-001",
      "text": "Production server at 10.0.1.50, SSH via bastion on port 2222",
      "added": "2026-03-15T10:30:00Z",
      "context": {
        "phase": "03-deployment",
        "file": "deploy/config.yml"
      },
      "classification": {
        "audience": "devops",
        "document": "OPERATIONS",
        "section": "Infrastructure",
        "confidence": "high"
      },
      "status": "pending"
    },
    {
      "id": "NOTE-002",
      "text": "Flows should only be called once during tests — calling twice causes duplicate DB entries",
      "added": "2026-03-15T11:15:00Z",
      "context": {
        "phase": "04-testing",
        "file": "tests/test_flows.py"
      },
      "classification": {
        "audience": "agents",
        "document": "GOTCHAS",
        "section": null,
        "confidence": "medium"
      },
      "status": "pending"
    }
  ]
}
```

### Integration During `/mg:create-docs`

During the generate step, classified notes are:
1. Presented to the user for approval (audience, document, section assignment)
2. Expanded from raw note into proper prose matching the target document's style
3. Inserted at the classified location
4. Marked as `"status": "integrated"` in the inbox with the integration date

---

## GSD Integration

### Post-Milestone Workflow

1. User completes a milestone via GSD
2. User runs `/mg:create-docs`
3. Scan step reads all phase SUMMARY.md files from the completed milestone:
   - What was built (accomplishments)
   - What changed from plan (deviations)
   - What decisions were made (runtime choices)
   - What requirements were completed
4. REQUIREMENTS.md traceability tells the scan which features are new
5. VERIFICATION.md highlights gaps and edge cases worth documenting
6. Writer agents produce targeted section updates (not full rewrites)
7. Notes accumulated during the milestone via `/mg:add-docs` get integrated

### During Development

- `/mg:add-docs` captures operational knowledge as it's discovered
- Notes carry GSD phase context for better classification routing

### Backlog Integration

Documentation gaps found by the verify step can optionally be added to `.planning/BACKLOG.md` as documentation debt items.

---

## Workspace Directory Structure

### Output Directory (committed to git)

```
docs/auto-doc/
├── OVERVIEW.md                     ← Shared: business context, system summary, audience routing
├── GLOSSARY.md                     ← Shared: term definitions (source of truth for terminology)
│
├── end-users/
│   ├── USER_GUIDE.md               ← Task-oriented how-to articles
│   └── [domain-specific].md        ← Project-specific (defined in config)
│
├── developers/
│   ├── ARCHITECTURE.md             ← System design, data model, ADRs
│   ├── DEVELOPER_GUIDE.md          ← Code examples, extension patterns, common tasks
│   └── QUICK_REFERENCE.md          ← Cheat sheet: paths, commands, lookups
│
├── agents/
│   ├── SYSTEM_MAP.md               ← Component registry with file paths + API surface
│   ├── CONVENTIONS.md              ← Code patterns, naming, do/don't rules
│   ├── GOTCHAS.md                  ← Edge cases, ordering constraints, invariants
│   └── TESTING.md                  ← Test patterns, isolation, fixtures
│
└── devops/
    ├── OPERATIONS.md               ← Deployment, service management, config
    └── TROUBLESHOOTING.md          ← Symptom → cause → fix runbook entries
```

### Tool Workspace (gitignored or project-local)

```
.mg/docs/
├── .docs.config.json               ← Project-level config overrides
├── notes-inbox.json                 ← Captured notes awaiting integration
├── docs-scan.json                   ← Latest scan results (shared data contract)
├── docs-update-report.md           ← What was changed in last generate run
├── docs-verify-report.md           ← Verification issues from last verify run
└── scan-logs/
    ├── scan-orientation.md          ← Project understanding from scan
    ├── scan-end-users.md            ← End-user audience analysis
    ├── scan-developers.md           ← Developer audience analysis
    ├── scan-agents.md               ← Agent audience analysis
    └── scan-devops.md               ← DevOps audience analysis
```

---

## Tool Source Directory Structure

```
docs/
├── install.sh
├── commands/
│   ├── create-docs.md              ← Entry point / router (detects state, routes to step)
│   ├── create-docs-scan.md         ← Step 1: orientation + source material index + staleness
│   ├── create-docs-generate.md     ← Step 2: section-by-section generation with approval
│   ├── create-docs-verify.md       ← Step 3: cross-reference + Diataxis + completeness
│   └── add-docs.md                 ← Quick note capture + auto-classification
├── agents/
│   ├── TEMPLATE.md                 ← Writer agent template (shared pattern for all writers)
│   ├── end-user-writer.md          ← End-user audience writing guidance + conventions
│   ├── developer-writer.md         ← Developer audience writing guidance + conventions
│   ├── agent-writer.md             ← Agent audience writing guidance + conventions
│   ├── devops-writer.md            ← DevOps audience writing guidance + conventions
│   ├── glossary-writer.md          ← Glossary reconciliation + terminology consistency
│   ├── staleness-scanner.md        ← Staleness detection per section
│   └── verifier.md                 ← Cross-reference + Diataxis + completeness checking
├── scripts/
│   ├── add-note.py                 ← Atomic append to notes-inbox.json
│   ├── classify-note.py            ← Deterministic heuristics for note classification
│   ├── check-references.py         ← Verify file paths + symbol names in docs exist
│   ├── merge-scan.py               ← Merge per-audience scan results into docs-scan.json
│   ├── staleness-check.py          ← Git-based section freshness analysis
│   └── lib/
│       └── ...                     ← Shared utilities (JSON I/O, git helpers)
└── references/
    ├── schema.md                   ← Data contract (docs-scan.json format)
    ├── style-guide.md              ← Cross-audience writing conventions
    ├── .docs.config.json           ← Global default configuration
    └── templates/
        ├── OVERVIEW.template.md
        ├── GLOSSARY.template.md
        ├── end-users/
        │   ├── USER_GUIDE.template.md
        │   └── DOMAIN_SPECIFIC.template.md
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

---

## Configuration

### Global Defaults (`.docs.config.json`)

```json
{
  "docs_dir": "docs/auto-doc",
  "audiences": {
    "end-users": {
      "enabled": true,
      "documents": ["USER_GUIDE"]
    },
    "developers": {
      "enabled": true,
      "documents": ["ARCHITECTURE", "DEVELOPER_GUIDE", "QUICK_REFERENCE"]
    },
    "agents": {
      "enabled": true,
      "documents": ["SYSTEM_MAP", "CONVENTIONS", "GOTCHAS", "TESTING"]
    },
    "devops": {
      "enabled": true,
      "documents": ["OPERATIONS", "TROUBLESHOOTING"]
    }
  },
  "shared_documents": ["OVERVIEW", "GLOSSARY"],
  "custom_documents": [],
  "gsd_integration": true
}
```

### Project Overrides (`.mg/docs/.docs.config.json`)

Projects can override any setting. Common overrides:
- Disable an audience: `"devops": { "enabled": false }` (for libraries without ops concerns)
- Add custom documents: `"custom_documents": [{ "name": "EXCEL_FORMAT", "audience": "end-users", "description": "KPI input file specification" }]`
- Change docs directory: `"docs_dir": "documentation"`
- Disable GSD integration: `"gsd_integration": false`

Config merge behavior: project fields override global, missing fields fall back to global defaults (same pattern as codebase-health).

---

## Install Script Behavior

Follows the standard mg-cc-tools install pattern:

### Modes
- `./install.sh --project [<dir>]` — Install to `<dir>/.claude/` + scaffold `.mg/docs/`
- `./install.sh --global` — Install to `~/.claude/`
- `./install.sh --target <path>` — Install to custom `.claude/` path

### What Gets Installed

1. **Commands** → `.claude/commands/mg/create-docs.md`, `create-docs-scan.md`, `create-docs-generate.md`, `create-docs-verify.md`, `add-docs.md`
2. **Agents** → `.claude/docs/agents/` (all 8 agent files)
3. **Scripts** → `.claude/docs/scripts/` (all Python helpers + lib/)
4. **References** → `.claude/docs/references/` (schema, style guide, config, templates/)

### Path Resolution (sed replacements)

| Placeholder | Resolved To |
|---|---|
| `agents/` (in commands) | Absolute path to `.claude/docs/agents/` |
| `{SCRIPTS_DIR}` | Absolute path to `.claude/docs/scripts/` |
| `{TEMPLATES_DIR}` | Absolute path to `.claude/docs/references/templates/` |
| `{GLOBAL_CONFIG}` | Absolute path to `.claude/docs/references/.docs.config.json` |
| `references/schema.md` | Absolute path to `.claude/docs/references/schema.md` |
| `references/style-guide.md` | Absolute path to `.claude/docs/references/style-guide.md` |

### Project Scaffolding (--project mode)

Creates `.mg/docs/` with:
- `.docs.config.json` (copy of global defaults for user to customize)
- `notes-inbox.json` (empty: `{"notes": []}`)
- `scan-logs/` directory

---

## Data Contract: `docs-scan.json`

The shared data contract between scan, generate, and verify steps. Full schema to be defined in `references/schema.md` (following the codebase-health pattern), but the key structure:

```json
{
  "project": "project-name",
  "scan_date": "2026-03-15T10:00:00Z",
  "root_path": "/absolute/path/to/project",
  "mode": "initial|update",
  "project_model": {
    "tech_stack": ["python", "prefect", "streamlit", "postgresql"],
    "entry_points": ["src/main.py", "src/app.py"],
    "components": [
      {
        "name": "Scoring Engine",
        "path": "src/scoring/",
        "purpose": "Evaluates stocks against archetype rulesets",
        "public_api": ["HybridScorer.score()", "HybridScorer.batch_score()"],
        "dependencies": ["src/models/", "src/data/"],
        "database_tables": ["scoring_results", "scoring_details"]
      }
    ],
    "infrastructure": {
      "deployment": ["docker-compose", "systemd"],
      "databases": ["postgresql"],
      "external_services": ["openai-api"],
      "ci_cd": ["github-actions"]
    }
  },
  "source_material_index": {
    "devops/OPERATIONS.md": {
      "Infrastructure": {
        "sources": ["deploy/docker-compose.yml", ".env.example"],
        "staleness": null
      }
    }
  },
  "staleness_report": [
    {
      "document": "developers/ARCHITECTURE.md",
      "section": "Database Schema",
      "reason": "alembic migration added 2 new columns since last update",
      "changed_files": ["alembic/versions/abc123_add_columns.py"],
      "severity": "medium",
      "suggested_action": "Update schema documentation to include new columns"
    }
  ],
  "note_classifications": [
    {
      "note_id": "NOTE-001",
      "audience": "devops",
      "document": "OPERATIONS",
      "section": "Infrastructure",
      "confidence": "high"
    }
  ],
  "gap_analysis": {
    "undocumented_components": ["src/cache/", "src/migrations/"],
    "missing_for_audience": {
      "agents": ["No GOTCHAS.md entries for cache invalidation"],
      "devops": ["No troubleshooting entry for database connection failures"]
    }
  },
  "gsd_context": {
    "milestone": "v12",
    "completed_phases": ["75-kpi-ingestion", "76-validation", "77-pipeline"],
    "deviations": ["Phase 76 added retry logic not in original plan"],
    "new_requirements_completed": ["REQ-75-01", "REQ-76-01", "REQ-77-01"]
  }
}
```

---

## Research Backing

### Format Research (per audience)

| Decision | Evidence | Source |
|---|---|---|
| End users: scannable > prose | 58% usability improvement | NNGroup |
| End users: max 7 steps/procedure | Internal testing data | Microsoft Style Guide |
| Developers: code examples #1 | Developer survey rankings | SmartBear |
| Developers: Diataxis type separation | Framework adoption by 100s of projects | diataxis.fr |
| DevOps: runbook structure | SRE best practices | Google SRE Book, PagerDuty |
| Agents: Markdown over JSON/YAML | 15-16% more token efficient | OpenAI community analysis |
| Agents: AGENTS.md reduces runtime | 28.64% median reduction | arXiv 2601.20404 |
| Agents: three-tier architecture | 283 development sessions | arXiv 2602.20478 (Codified Context) |

### Template Depth Research

| Decision | Evidence | Source |
|---|---|---|
| Purpose statements per section | Differentiates mediocre from good LLM output | TGDP finding |
| Concrete examples per section | Single most impactful element | Tom Johnson (I'd Rather Be Writing) |
| Section-by-section generation | Better than whole-document | Tom Johnson |
| Source material alongside template | Prevents hallucination | Tom Johnson, Eugene Yan |
| Optional section markers | Prevents empty boilerplate | TGDP, GitLab |
| No word count constraints | Produces padding/truncation | Multiple sources |

### JSON vs YAML vs Markdown for Agents

| Finding | Result | Source |
|---|---|---|
| YAML comprehension accuracy | Best on 2/3 models tested | ImprovingAgents benchmark |
| JSON generation accuracy | 99.26% vs YAML 95.26% | StructEval (arXiv 2505.20139) |
| YAML token cost vs JSON | 6-10% MORE tokens (myth busted) | tiktoken analysis, 6 models |
| Markdown token efficiency | 15-16% fewer than pretty-printed JSON | OpenAI community |
| Structured output reasoning penalty | 10-15% degradation in JSON-mode | arXiv 2408.02442 |
| Industry standard for AI docs | Markdown (CLAUDE.md, AGENTS.md, .cursor/) | Universal adoption |

---

## Relationship to Existing mg-cc-tools

### Follows Codebase-Health Pattern

The docs tool mirrors codebase-health's architecture:
- 3-step pipeline (scan → generate → verify, like scan → verify → implement)
- Shared JSON data contract between steps
- Parallel subagents per category (audiences instead of health categories)
- Python scripts for deterministic operations (JSON I/O, reference checking)
- Config layering (global defaults + project overrides)
- State detection for pipeline resumption
- `.mg/docs/` workspace (like `.mg/health-scan/`)

**Key files to study as implementation exemplars:**
- Router / state detection: `codebase-health/commands/codebase-health.md`
- Install script with sed replacements: `codebase-health/install.sh`
- Scan orchestration + agent spawning: `codebase-health/commands/codebase-health-scan.md`
- Agent template pattern: `codebase-health/agents/TEMPLATE.md`
- Atomic JSON I/O scripts: `codebase-health/scripts/add-finding.py`
- Schema definition format: `codebase-health/references/schema.md`
- Config layering logic: `codebase-health/commands/codebase-health-scan.md` (config merge section)
- Verification step: `codebase-health/commands/codebase-health-verify.md`

### Differences from Codebase-Health

- Step 2 is **creative** (writing docs), not diagnostic (verifying findings)
- Has an approval gate between scan and generate (staleness report review)
- Has a companion command (`/mg:add-docs`) for incremental note capture
- Templates drive generation (codebase-health uses agent specialization)
- Output is committed documentation (not a findings JSON + reports)

### GSD Integration (like debug-triage, update-backlog)

- Reads `.planning/` state when available
- Designed to run post-milestone
- Can feed documentation gaps back to BACKLOG.md
- Notes carry GSD phase context

---

## Open Items for Implementation Planning

1. **Template authoring** — Each of the ~13 templates needs the three-layer content (heading + purpose + example). This is the bulk of creative work.
2. **Schema definition** — Full `docs-scan.json` schema in `references/schema.md` (JSON Schema or structured markdown like codebase-health).
3. **Style guide** — Cross-audience writing conventions document for `references/style-guide.md`.
4. **Agent prompt design** — How writer agents receive templates + source material + existing content. Context budget management for large projects.
5. **Section-by-section generation protocol** — Exact mechanism for feeding one section at a time to the writer agent (sequential within an agent, parallel across audiences).
6. **Staleness detection granularity** — How `docs-meta` comments map to git blame for freshness checking. Edge cases with reformatted files.
7. **Custom document support** — How project-specific documents get templates (user-provided? generated from description?).
8. **Testing strategy** — Unit tests for Python scripts, integration tests for the pipeline.
