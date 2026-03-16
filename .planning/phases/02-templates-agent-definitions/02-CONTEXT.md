# Phase 2: Templates & Agent Definitions - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning
**Source:** Merged — Context import (docs/work-queue/todo/doc-command/phase-docs/phase-02-templates-agent-definitions.md) + milestone discussion (cross-cutting pass)

<domain>
## Phase Boundary

All static content files (templates and agent prompts) are authored so the pipeline can use them for generation. This includes ~13 templates with three-layer architecture, 7 agent definitions, and parallel execution setup.

</domain>

<decisions>
## Implementation Decisions

### Three-Layer Template Architecture (TPL-01)
- Layer 1 — Classification: each template tagged with Diataxis type (tutorial, how-to, reference, explanation) telling the writer agent what principles to follow
- Layer 2 — Structural: section headings with purpose statement per section (1-2 sentences explaining *why* the section exists). Critical differentiator for LLM output quality.
- Layer 3 — Exemplar: one concrete example per section showing what "good" looks like. Single most impactful element per Tom Johnson research.
- Template file format: Markdown with HTML comments containing purpose statements and examples. Comments stripped from final output.
- Optional sections marked with `<!-- OPTIONAL — delete if not applicable -->`
- No word count constraints — they produce padding or truncation

### Template Inventory (~13 templates, TPL-02)
- Shared: `OVERVIEW.template.md`, `GLOSSARY.template.md`
- End-users: `USER_GUIDE.template.md`, `DOMAIN_SPECIFIC.template.md`
- Developers: `ARCHITECTURE.template.md`, `DEVELOPER_GUIDE.template.md`, `QUICK_REFERENCE.template.md`
- Agents: `SYSTEM_MAP.template.md`, `CONVENTIONS.template.md`, `GOTCHAS.template.md`, `TESTING.template.md`
- DevOps: `OPERATIONS.template.md`, `TROUBLESHOOTING.template.md`
- All live in `references/templates/` organized by audience subdirectory

### Optional Section Markers (TPL-03)
- Every template with applicable optional sections must include `<!-- OPTIONAL -->` comments
- Prevents empty boilerplate in generated docs

### End-User Writer Agent (AGT-01)
- Audience: non-technical users (portfolio managers, business analysts, internal platform users)
- Format conventions: plain language, no jargon, active voice, scannable formatting (58% usability improvement per NNGroup), numbered steps with one action per step, max 7 steps per procedure, tables for comparisons, progressive disclosure, task-oriented structure ("How do I..."), not by system module
- Documents covered: USER_GUIDE.md, domain-specific docs

### Developer Writer Agent (AGT-02)
- Audience: software engineers who maintain and extend the codebase
- Format conventions: code examples are #1 priority (SmartBear), interleave prose and code, organize by developer goal not internal API, separate Diataxis types (never mix), fenced code blocks with language tags, copy-paste-ready, "I want to..." lookup tables
- Documents covered: ARCHITECTURE.md, DEVELOPER_GUIDE.md, QUICK_REFERENCE.md
- Stripe/Twilio-style docs where code examples are primary

### Agent Writer Agent (AGT-03)
- Audience: AI coding assistants (Claude Code, Copilot, Cursor, etc.)
- Format conventions: Markdown with YAML frontmatter, explicit over implicit (exact names not pronouns), consistent terminology, tables for structured data, unique heading names (avoids embedding overlap), separate sections for distinct topics (prevents chunking problems)
- Follows "Codified Context" three-tier architecture (arXiv:2602.20478)
- Documents covered: SYSTEM_MAP.md, CONVENTIONS.md, GOTCHAS.md, TESTING.md
- Markdown chosen over JSON/YAML: 15-16% more token-efficient, AGENTS.md correlates with 28.64% runtime reduction

### DevOps Writer Agent (AGT-04)
- Audience: people who deploy, monitor, and troubleshoot in production
- Format conventions: runbook structure (alert/trigger → severity → pre-checks → steps → verification → escalation), concrete commands with full syntax, decision trees and checklists over prose, every deployment includes matching rollback, copy-paste-ready, ASCII diagrams only
- Documents covered: OPERATIONS.md, TROUBLESHOOTING.md
- Backed by PagerDuty, Google SRE Book, AWS Well-Architected

### Glossary Writer Agent (AGT-05)
- Role: glossary reconciliation + terminology consistency
- Receives proposed new terms from all writer agents
- Reconciles and updates GLOSSARY.md as terminology source of truth

### Staleness Scanner Agent (AGT-06)
- Role: staleness detection per section
- Used during scan pipeline (Phase 3) for per-section freshness analysis

### Verifier Agent (AGT-07)
- Role: cross-reference + Diataxis + completeness checking
- Used during verify pipeline (Phase 5)

### Parallel Execution (AGT-08)
- Writer agents run in parallel: one per audience (4 total) plus glossary agent
- OVERVIEW.md generated last (after all subdirs complete) for accurate routing

### Shared Documents
- OVERVIEW.md: business purpose, system-level architecture summary, key concepts, audience routing. The "landing page" that avoids repeating context.
- GLOSSARY.md: complete term definitions by category (system concepts, domain terms, technical terms). Source of truth for terminology — all writer agents must use glossary terms consistently.

### Cross-Cutting Decisions
- Tool installs to `.claude/create-docs/` — templates at `.claude/create-docs/references/templates/`, agents at `.claude/create-docs/agents/` *(from milestone discussion)* ⚠️ CONFLICTS WITH: existing references to `.claude/docs/` in Integration Points — update all paths to `.claude/create-docs/`
- Agents receive file paths only, read files themselves — no pasting of templates/source material into agent prompts *(from milestone discussion)*
- Generate execution order: (1) glossary agent first, (2) 4 writer agents in parallel, (3) glossary reconciliation pass, (4) OVERVIEW.md last *(from milestone discussion)* ⚠️ CONFLICTS WITH: "Writer agents run in parallel: one per audience (4 total) plus glossary agent" in Parallel Execution section — glossary is now sequential, not parallel with writers
- Writers propose terms only (term + one-line context note), glossary agent writes all definitions *(from milestone discussion)*
- Custom document templates not needed for v1 — DOC-04 deferred to v2 *(from milestone discussion)*
- Road-runner validation baked into phase success criteria — agent definitions must work correctly when run against `../road-runner` *(from milestone discussion)*

### Claude's Discretion
- Internal structure of each agent prompt (how to organize instructions within each .md file)
- TEMPLATE.md shared pattern design — how to structure the common pattern all writers follow
- Exact exemplar content for each template section (the "Layer 3" creative work)
- How staleness-scanner and verifier agents integrate with their respective pipeline steps

</decisions>

<specifics>
## Specific Ideas

- Follow codebase-health agent patterns as implementation exemplars:
  - Agent template pattern: `codebase-health/agents/TEMPLATE.md`
  - Audience-specific agent examples: `codebase-health/agents/orphaned-code.md`, `codebase-health/agents/sprawling-code.md`
  - How agents are spawned with pasted prompts: `codebase-health/commands/codebase-health-scan.md`
- Template file format uses HTML comments (`<!-- PURPOSE: ... -->`, `<!-- EXAMPLE: ... -->`) that are stripped from final output
- Research backing should inform template and agent design decisions (format research tables, template depth research, JSON vs YAML analysis)
- Template authoring is the bulk of creative work — each of ~13 templates needs three-layer content

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `codebase-health/agents/TEMPLATE.md`: Reference pattern for shared agent template
- `codebase-health/agents/orphaned-code.md`, `sprawling-code.md`: Examples of audience-specific agent definitions
- `codebase-health/commands/codebase-health-scan.md`: Pattern for spawning agents with pasted prompts

### Established Patterns
- Agents are .md files with instructions that get spawned as subagents via the Task tool
- Each agent follows a shared TEMPLATE.md pattern with specialization
- Parallel agent execution with coordination (one per category)

### Integration Points
- Templates land at `.claude/docs/references/templates/` (organized by audience)
- Agent definitions land at `.claude/docs/agents/`
- Writer agents are spawned by the generate command (Phase 4)
- Staleness scanner is spawned by the scan command (Phase 3)
- Verifier is spawned by the verify command (Phase 5)

</code_context>

<deferred>
## Deferred Ideas

- Testing strategy for agent prompt quality — cross-cutting open item
- Template versioning (for future updates) — not in v1 scope

</deferred>

---

*Phase: 02-templates-agent-definitions*
*Context gathered: 2026-03-16 via context import*
