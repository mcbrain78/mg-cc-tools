# Phase 2: Templates & Agent Definitions

> Source: docs/work-queue/todo/doc-command/DESIGN.md
> Phase goal: All static content files (templates and agent prompts) are authored so the pipeline can use them for generation
> Requirements: TPL-01, TPL-02, TPL-03, AGT-01, AGT-02, AGT-03, AGT-04, AGT-05, AGT-06, AGT-07, AGT-08

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

## Tool Source Directory Structure (agents and templates)

```
docs/
├── agents/
│   ├── TEMPLATE.md                 ← Writer agent template (shared pattern for all writers)
│   ├── end-user-writer.md          ← End-user audience writing guidance + conventions
│   ├── developer-writer.md         ← Developer audience writing guidance + conventions
│   ├── agent-writer.md             ← Agent audience writing guidance + conventions
│   ├── devops-writer.md            ← DevOps audience writing guidance + conventions
│   ├── glossary-writer.md          ← Glossary reconciliation + terminology consistency
│   ├── staleness-scanner.md        ← Staleness detection per section
│   └── verifier.md                 ← Cross-reference + Diataxis + completeness checking
└── references/
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

[See Phase 1 for scripts/ and references/ (non-template) directory structure]

---

## Open Items (Phase 2)

1. **Template authoring** — Each of the ~13 templates needs the three-layer content (heading + purpose + example). This is the bulk of creative work.
4. **Agent prompt design** — How writer agents receive templates + source material + existing content. Context budget management for large projects.

---

## Additional Context

### Purpose

A documentation tool that scans a project and generates/maintains audience-segmented documentation. It integrates with the GSD milestone lifecycle so documentation stays current as the project evolves, and provides a lightweight note-capture command for recording operational knowledge during development.

### Problem Statement

Documentation is manually created (see `ai-stock-ranker/docs/documentation_v3/` for an example of what the user produces by hand). This is time-consuming, falls out of date as code changes, and lacks systematic coverage across audiences. Different consumers of documentation (end users, developers, AI agents, operations staff) need fundamentally different content, formats, and depth levels — but maintaining 4 parallel documentation sets manually is impractical.

### Relationship to Existing mg-cc-tools

#### Follows Codebase-Health Pattern

The docs tool mirrors codebase-health's architecture:
- 3-step pipeline (scan → generate → verify, like scan → verify → implement)
- Shared JSON data contract between steps
- Parallel subagents per category (audiences instead of health categories)
- Python scripts for deterministic operations (JSON I/O, reference checking)
- Config layering (global defaults + project overrides)
- State detection for pipeline resumption
- `.mg/docs/` workspace (like `.mg/health-scan/`)

**Key files to study as implementation exemplars:**
- Agent template pattern: `codebase-health/agents/TEMPLATE.md`
- Audience-specific agent examples: `codebase-health/agents/orphaned-code.md`, `codebase-health/agents/sprawling-code.md`
- How agents are spawned with pasted prompts: `codebase-health/commands/codebase-health-scan.md`

#### Differences from Codebase-Health

- Step 2 is **creative** (writing docs), not diagnostic (verifying findings)
- Has an approval gate between scan and generate (staleness report review)
- Has a companion command (`/mg:add-docs`) for incremental note capture
- Templates drive generation (codebase-health uses agent specialization)
- Output is committed documentation (not a findings JSON + reports)

#### GSD Integration (like debug-triage, update-backlog)

- Reads `.planning/` state when available
- Designed to run post-milestone
- Can feed documentation gaps back to BACKLOG.md
- Notes carry GSD phase context

### Open Item #8

8. **Testing strategy** — Unit tests for Python scripts, integration tests for the pipeline.

---

*Prepared from: docs/work-queue/todo/doc-command/DESIGN.md*
*Phase: 02-templates-agent-definitions*
*Date: 2026-03-16*
