# Phase 15: Auto Doc Enduser Quality - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning
**Source:** Context import (docs/work-queue/auto-doc-1.1/phase-4-end-user-quality.md) + discussion 2026-03-22

<domain>
## Phase Boundary

Make end-user documentation functional and interface-aware. Document through the user's actual interface (web UI, CLI, etc.) instead of defaulting to bash commands. Add functional context (what, why) before procedures (how). Can run in parallel with Phase 14 (reference manifest) — independent work streams.

</domain>

<decisions>
## Implementation Decisions

### Interface detection in scan
- Scan phase identifies the primary user interface as part of the project model
- Priority chain: (1) explicit config in `.docs.config.json` `user_interfaces` field — no detection, no confirmation; (2) heuristic detection + user confirmation via `AskUserQuestion`
- Heuristic principles: front-end frameworks with routes/templates → `web`; CLI frameworks (argument parsers, command groups) → `cli`; API-only frameworks without UI layer → `api`; orchestration platforms with dashboards → `web`; disambiguate with directory structure (`templates/`, `static/`, `pages/`, `app/` → web UI)
- When heuristics run, present detected interfaces to user: "Detected primary interface: **[name]** ([type]). Secondary: **[name]**. Is this correct?"
- Schema addition: `project_model` in `docs-scan.json` gains `user_interfaces` array with objects `{type, name, url_pattern, primary}`
- Placement: interface detection is a sub-step within Step 1 (Orient), performed by the orchestrator (not a subagent), as the last analysis step before writing `scan-project.json`
- Add `AskUserQuestion` to the scan command's `allowed-tools`

### Interface detection confirmation chain
1. User confirms → write to `scan-project.json` and persist to `.mg/docs/.docs.config.json` so subsequent scans don't re-ask
2. User corrects → use corrected values, persist to config
3. User absent / non-interactive → fall back to no `user_interfaces` (field absent). Writer falls back to CLI-style docs, matching current behavior. No blocking.

### Writer consumes user_interfaces
- Writer's Process section gains new step between "Read context" and "For each document": read `project_model.user_interfaces`, identify primary interface, all procedures default to this interface's style
- `type: "web"` → describe click paths, form fields, screen states
- `type: "cli"` → describe commands, flags, expected output
- `type: "api"` → describe requests, responses, status codes
- Secondary interfaces appear as `> **Power user tip:** ...` callouts
- No orchestrator changes needed — generate already passes `scan_data_path` to writer, writer already reads full scan data JSON

### Per-audience source material exclusion rules
- Add to `scan-audience.md` for end-users audience:
  - **Exclusions:** NEVER index for end-user docs: package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`), database schemas/migrations (`alembic/`, `migrations/`), system service files (`systemd/`, `Procfile`, `docker-compose.yml`), CI configs (`.github/`, `.gitlab-ci.yml`), environment files (`.env`, `.env.example`), internal API modules, test infrastructure (`tests/`, `conftest.py`)
  - **Inclusions:** Prefer: user-facing entry points, README usage sections, user config files, workflow/flow definitions, error message strings, UI templates, route handlers

### Refined PURPOSE comments in USER_GUIDE template
- Getting Started PURPOSE changes from generic "walk the user through first-time setup" to: "Walk the user through their first interaction with the running system. Assume infrastructure is already deployed. Focus on the user's interface (web UI, CLI, etc.), not installation or deployment."
- This alone prevents `pyproject.toml`, `systemd/*.service`, `.env.example` from being indexed

### Template restructuring — functional layer first
- Current: Getting Started → Common Tasks → Configuration → Troubleshooting
- New structure: Overview → Key Concepts → Workflows → Getting Started (first use, not first install) → Common Tasks → Configuration (user-facing only) → Troubleshooting
- Overview, Key Concepts, and Workflows are synthesized sections (don't map to source files)

### No update-mode migration needed
- Old end-user docs generated with the previous template structure will simply be deleted
- Fresh generation with the new 7-section template — no additive merge or migration path required

### SYNTHESIZED template comment pattern
- New `<!-- SYNTHESIZED: field1, field2 -->` comment for sections that generate from project model fields instead of source files
- Scan agent parsing rules:
  1. Split value on commas, trim whitespace to get field list (dotted paths into scan data)
  2. Skip source-file search entirely (no Glob/Grep)
  3. Write index entry with `"source_files": []` and `"synthesized_from": [field list]`
  4. MUST always produce the entry — its presence triggers the writer's synthesis path
- No validation of field paths at scan time
- Mark synthesized sections as non-optional (no `<!-- OPTIONAL -->` marker)
- `schema.md` needs `synthesized_from` as optional string-array field on source_material_index entries
- Writer fallback: "If `synthesized_from` is present and `source_files` is empty, generate from the named project model fields"
- Staleness: synthesized sections use `sources: []` in `docs-meta`, which `staleness-check.py` treats as fresh (returns `None` for empty sources) — no Python script changes needed

### BOUNDARY template comment pattern
- Format: `<!-- BOUNDARY: Infrastructure setup belongs in devops/OPERATIONS.md, not here. -->`
- Negative guidance for both scan agent (don't index infrastructure files for this section) and writer (don't generate infrastructure content, cross-reference the named alternate document instead)
- Both agents need explicit handling added

### Synthesized section quality control
- Generate purely from structured scan data fields — no source file reading, no LLM inference beyond field contents
- If `project_model` lacks enough data (no components, no entry points), writer emits `<!-- TODO: needs manual input — insufficient scan data for this section -->` placeholder
- Prevents hallucinated capabilities at cost of sometimes producing thin sections

### New section exemplars
- Each of the 3 new synthesized sections (Overview, Key Concepts, Workflows) gets its own tailored EXAMPLE comment
- All exemplars use the road-runner portfolio analytics domain (same as the 4 existing sections) for consistency
- Exemplars show web-UI style as reference case (matches existing sections)
- **Overview exemplar**: guide-level introduction — what this guide covers and what the user will gain from reading it. NOT a product overview or routing page (that's OVERVIEW.md's job). SYNTHESIZED from project model capabilities and user_interfaces.
- **Key Concepts exemplar**: domain + interaction concepts — both what things are (portfolio, scoring model, rebalancing signal) and how users interact with them (scoring run, dashboard view). Bridges domain vocabulary with user actions.
- **Workflows exemplar**: high-level journey maps — each workflow is a named end-to-end journey (e.g., "Quarterly Portfolio Review") with 3-5 numbered high-level steps that link to detailed procedures in Common Tasks. Workflows serve as a navigation layer, not a duplicate of procedures.

### Replacement template exemplars (existing sections)
- Current exemplars are entirely CLI-centric — writer imitates exemplars directly ("Read the `<!-- EXAMPLE: ... -->` comment to understand what 'good' looks like")
- Replace ALL exemplars in USER_GUIDE.template.md with functional-first, interface-aware versions
- Exemplars show web-UI style as reference case (hardest to get right, most common failure mode)
- Exemplars are static (don't change per-project)
- Explicit writer guidance: "Exemplars demonstrate web-UI style. If primary interface is CLI or API, follow same structure — functional context before procedure, expected results after steps — but use commands/responses instead of click paths"
- Getting Started exemplar: open dashboard, add first stock, understand the score (with power user CLI tip)
- Common Tasks exemplar: update quarterly data (goal-first, then click-path steps, then expected results), export portfolio report
- Configuration exemplar: user settings table (scoring model, alert threshold, visibility), changing tracked stocks via UI
- Troubleshooting exemplar: "No data found" with likely cause + what to do steps, "Scores show N/A"

### Overview section vs shared OVERVIEW.md
- **OVERVIEW.md** (shared document): cross-audience routing page — "developers go here, end-users go here, devops go here"
- **USER_GUIDE Overview section**: guide-level introduction — what this guide covers and what the reader will gain from it
- Distinct purposes, no overlap — OVERVIEW.md routes between audiences, USER_GUIDE Overview orients within the end-user guide
- USER_GUIDE Overview is SYNTHESIZED (generated from project model fields, not source files)

### Writer agent guidance — functional-first pattern
- Document through the primary interface (web → click paths, CLI → commands)
- Before any procedure, explain the goal (what is the user accomplishing, why)
- After the goal, explain what the system will do (duration, what happens, what to expect)
- Then the steps through the user's interface
- Secondary interface as a tip
- Expected results should be what the user sees (for web: "The run appears in the dashboard with status 'Running'")
- Cross-reference devops guide for infrastructure setup, don't inline it

### Cross-audience boundary enforcement
- Installation and infrastructure setup → devops OPERATIONS.md
- API details and internal architecture → developer ARCHITECTURE.md
- System configuration → devops OPERATIONS.md
- User-facing configuration → stays in USER_GUIDE.md

### Projects where end-users ARE developers
- Not a configuration problem — user simply doesn't enable `end-users` audience in `.docs.config.json`
- The developer guide IS the user guide in that case
- No configurable profile needed

### Delete DOMAIN_SPECIFIC.template.md
- Remove `auto-doc/references/templates/end-users/DOMAIN_SPECIFIC.template.md` from v1.1 scope
- Add back when a real use case requires it

### No Python script changes
- `write-scan-output.py` validates key format only (`DOCUMENT/section-slug` pattern), not entry contents — `synthesized_from` passes through unvalidated
- `merge-scan.py` passes through `project_model` unchanged
- `staleness-check.py` treats empty sources as fresh

### Claude's Discretion
- Exact wording of BOUNDARY comments for each template section
- How to structure the scan agent's SYNTHESIZED parsing implementation
- Whether to add BOUNDARY comments to non-end-user templates as well
- How to handle edge cases where heuristic detection is ambiguous (multiple equally-likely interfaces)
- Internal organization of the end-user-writer.md agent rewrite
- Exact content of the 3 new synthesized section exemplars (within the constraints above)

</decisions>

<specifics>
## Specific Ideas

- The source document provides complete replacement exemplars for Getting Started, Common Tasks, Configuration, and Troubleshooting sections — use these verbatim in the template
- The `docs-meta` pattern with `sources: []` already works for synthesized sections — `staleness-check.py` returns `None` at line 149-150 for empty sources
- Merge behavior: only end-users audience scans USER_GUIDE sections, so synthesized entries won't collide during `merge-scan.py` dedup
- The source document's "Root Cause" analysis (infrastructure code indexed as source material + no interface awareness) directly maps to the two main fixes (exclusion rules + interface detection)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scan-audience.md` already scans per-audience using `<!-- PURPOSE -->` comments — SYNTHESIZED and BOUNDARY are extensions of this pattern
- Writer agents already read full scan data JSON via `scan_data_path` — `user_interfaces` is accessible without plumbing changes
- `staleness-check.py` empty-sources handling: already returns `None` for sections with no source files

### Established Patterns
- `<!-- PURPOSE: ... -->` template comment pattern: SYNTHESIZED and BOUNDARY follow the same HTML-comment-as-metadata approach
- Per-audience parallel execution: synthesized entries only appear in end-users scan, no cross-audience collisions
- `docs-meta` source tracking: `sources: []` for synthesized sections fits existing pattern

### Integration Points
- `auto-doc/references/templates/end-users/USER_GUIDE.template.md`: restructure + new exemplars + SYNTHESIZED/BOUNDARY comments
- `auto-doc/agents/end-user-writer.md`: interface-aware process step + synthesized_from fallback + BOUNDARY handling
- `auto-doc/agents/scan-audience.md`: exclusion rules + SYNTHESIZED parsing + BOUNDARY handling
- `auto-doc/commands/auto-doc-scan.md`: add AskUserQuestion to allowed-tools + interface detection step
- `auto-doc/references/schema.md`: user_interfaces + synthesized_from fields

</code_context>

<deferred>
## Deferred Ideas

- Multi-interface projects with more than 2 interfaces: current design handles primary + secondary tips. Projects with 3+ interfaces would need a more sophisticated approach — not expected in current target projects.
- Synthesized sections for non-end-user audiences: if developer or devops templates also need overview-style synthesized sections, the SYNTHESIZED pattern is reusable. Not in Phase 15 scope.

</deferred>

---

*Phase: 15-auto-doc-enduser-quality*
*Context gathered: 2026-03-22 via context import, updated 2026-03-22 via discussion*
