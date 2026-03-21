# Phase 4: End-User Documentation Quality — Functional Over Technical

**Goal:** Make end-user documentation functional and interface-aware. Document through the user's actual interface (web UI, CLI, etc.) instead of defaulting to bash commands. Add functional context (what, why) before procedures (how).

**Depends on:** Phase 1 (rename must complete — files use `auto-doc/` paths)
**Can run in parallel with:** Phase 3 (reference manifest) — independent work streams

---

## Problem Statement

The generated end-user documentation (USER_GUIDE.md) reads like a devops runbook. Observed on road-runner:

### 1. Setup is infrastructure, not onboarding

Getting Started includes 7 steps: `pip install -e ".[dev]"`, `alembic upgrade`, `prefect concurrency-limit create`. These are infrastructure tasks. An end-user guide should start from "the system is set up, here's how to use it."

### 2. Documents the wrong interface

The guide documents CLI commands (`prefect deployment run ...`) when the user's actual interface is the Prefect web dashboard. Users click "Deployments", find the flow, click "Run." The bash commands are the operator interface, not the user interface.

This is a general problem: the pipeline reads source code (inherently CLI/API-centric) and produces CLI-centric docs regardless of what the user actually interacts with. For a web app, the guide should describe click paths, form fields, UI states — not shell commands.

### 3. Common Tasks are command-centric, not goal-centric

Every task follows: "To do X, run this command." The functional context — what the user is accomplishing, why it matters — is minimal.

**Current:** "To trigger it manually: `prefect deployment run ingest-quarterly-finance-data/...`"

**Better:** "After each quarter ends, you need to update the financial data for all tracked stocks. This pulls in the latest earnings reports, balance sheets, and ownership changes. The update takes about 15 minutes. Open the Prefect dashboard, go to Deployments, and click Run on 'Quarterly Ingestion.'"

### 4. Configuration documents infrastructure, not user choices

DATABASE_URL, PREFECT_API_URL, FINRA_API_KEY — deployment settings, not user settings. An end-user cares about: which stocks to track, which scoring model to use, what thresholds trigger alerts.

### 5. No functional overview

The guide jumps straight into procedures without explaining what the system does.

---

## Root Cause

### 1. Source material is infrastructure code

The scan agent indexed `pyproject.toml`, `systemd/*.service`, `.env.example` as source material for the end-user guide. The writer faithfully documented them.

### 2. No awareness of the user's interface

The pipeline doesn't identify HOW users interact with the system. It defaults to CLI-centric docs. But users may interact through:

- **Web UI** (dashboards, admin panels, forms) → click paths, screen states
- **CLI** (command-line tools) → commands, flags, output
- **API** (REST/GraphQL endpoints) → requests, responses
- **Desktop app** (native applications) → menus, dialogs
- **Hybrid** (web UI primary, CLI secondary) → primary interface first

---

## Solution

### 1. Interface detection in scan

The scan phase identifies the primary user interface as part of the project model. Detection follows a priority chain — explicit config wins, heuristics are a fallback with user confirmation.

**Priority chain:**

1. **Explicit config** (highest priority): If `.docs.config.json` contains `user_interfaces`, use it directly. No detection, no confirmation.
2. **Heuristic detection + confirmation** (fallback): If no config exists, detect interfaces from project signals and present the result to the user via `AskUserQuestion` before writing to `docs-scan.json`. This requires adding `AskUserQuestion` to the scan command's `allowed-tools`.

**Heuristic principles** (the scan agent applies these to whatever frameworks the target project uses):

- **Front-end frameworks with routes or templates** → `web` (the user interacts through a browser)
- **CLI frameworks** (argument parsers, command groups) → `cli` (the user interacts through a terminal)
- **API-only frameworks without a UI layer** → `api` (the user interacts through HTTP requests)
- **Orchestration platforms with dashboards** → `web` (the dashboard is the user interface, not the underlying CLI)
- **Disambiguate with directory structure:** presence of `templates/`, `static/`, `pages/`, or `app/` directories signals a user-facing web UI. Absence of these in a web framework project signals API-only.

When heuristics run, present the detected interfaces to the user: "Detected primary interface: **[name]** ([type]). Secondary: **[name]**. Is this correct?" The user can correct before the scan writes `docs-scan.json`.

**Schema addition** — `project_model` in `docs-scan.json` gains `user_interfaces`:
```json
{
  "project_model": {
    "user_interfaces": [
      {"type": "web", "name": "Prefect Dashboard", "url_pattern": "http://{host}:4200", "primary": true},
      {"type": "cli", "name": "prefect CLI", "primary": false}
    ]
  }
}
```

**Consumer path** — the writer agent reads `project_model.user_interfaces` from scan data and uses the `primary: true` entry to determine documentation style:

- `type: "web"` → describe click paths, form fields, screen states
- `type: "cli"` → describe commands, flags, expected output
- `type: "api"` → describe requests, responses, status codes

Specifically, the writer's Process section gains a new step between "Read context" and "For each document": *"Read `project_model.user_interfaces`. Identify the primary interface. All procedures default to this interface's style. Secondary interfaces appear as tips."* The writer's "End-User-Specific Conventions" section gains: *"Document through the primary interface. If `user_interfaces` identifies a web UI as primary, describe click paths — not shell commands. Mention secondary interfaces as `> **Power user tip:** ...` callouts."*

No orchestrator changes needed — the generate command already passes `scan_data_path` to the writer, and the writer already reads the full scan data JSON. The `user_interfaces` data is accessible without plumbing changes.

**Placement in scan process:** Interface detection is a sub-step within Step 1 (Orient), as the last analysis step before writing output — after steps 2-12 (project structure, tech stack, entry points) and before step 14b (writing `scan-project.json`). The **orchestrator** performs detection, not a subagent — it already reads project structure and tech stack during Orient, so it has all inputs needed for interface heuristics. The detected `user_interfaces` array becomes part of the `project_model` written to `scan-project.json`, which `merge-scan.py` passes through to the final `docs-scan.json`.

**Confirmation and fallback chain:** When heuristics run (no explicit config), the orchestrator presents detected interfaces via `AskUserQuestion` and handles the response:

1. **User confirms** → write to `scan-project.json` and persist to `.mg/docs/.docs.config.json` so subsequent scans don't re-ask.
2. **User corrects** → use the corrected values, persist to config.
3. **User is absent / non-interactive** → fall back to no `user_interfaces` (field absent from project_model). The writer falls back to CLI-style docs, matching current behavior. No blocking.

### 2. Audience-aware source material filtering

The scan agent (`scan-audience.md`) already scans per-audience using each template section's `<!-- PURPOSE -->` comment. The problem is that it has no concrete exclusion rules — it relies on LLM judgment, which reasonably concludes that `pyproject.toml` is relevant to "Getting Started" because it contains install commands. Two concrete changes fix this:

**A. Per-audience exclusion rules added to `scan-audience.md`:**

For the `end-users` audience, add after the source-file search step:

> **End-user exclusions:** NEVER index these as source material for end-user documents: package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`), database schemas and migrations (`alembic/`, `migrations/`), system service files (`systemd/`, `Procfile`, `docker-compose.yml`), CI configs (`.github/`, `.gitlab-ci.yml`), environment files (`.env`, `.env.example`), internal API modules, test infrastructure (`tests/`, `conftest.py`). These belong in devops or developer audience scans.
>
> **End-user inclusions:** Prefer: user-facing entry points, README sections about usage, user config files, workflow/flow definitions, error message strings, UI templates, route handlers.

**B. Refined PURPOSE comments in `USER_GUIDE.template.md`:**

Current PURPOSE for Getting Started: generic "walk the user through first-time setup." This doesn't distinguish user setup from operator setup.

Change to: *"Walk the user through their first interaction with the running system. Assume infrastructure is already deployed. Focus on the user's interface (web UI, CLI, etc.), not installation or deployment."*

This alone prevents `pyproject.toml`, `systemd/*.service`, and `.env.example` from being indexed — they're installation/deployment artifacts, not first-interaction artifacts.

### 3. Template restructuring — functional layer first

Current:
```
Getting Started (setup) → Common Tasks → Configuration → Troubleshooting
```

Proposed:
```
Overview (what this system does for you)
  → Key Concepts (mental model — 3-5 concepts)
  → Workflows (high-level cycles: daily, quarterly, ad-hoc)
Getting Started (first use, not first install — assumes setup is done)
Common Tasks (procedures with functional context)
Configuration (user-facing settings only)
Troubleshooting
```

**Source material for synthesized sections:** Overview, Key Concepts, and Workflows don't map to specific source files — they're synthesized from the project model, glossary, and entry points. The current scan-then-write architecture assumes every section has indexable source files.

Fix: add a `<!-- SYNTHESIZED: field1, field2 -->` template comment for these sections instead of `<!-- PURPOSE: ... -->`. The scan agent handles them differently from source-material sections.

**Scan agent parsing rules for `SYNTHESIZED` comments:**

1. When the scan agent encounters `<!-- SYNTHESIZED: project_model.tech_stack, project_model.entry_points, project_model.components -->`, it splits the value on commas and trims whitespace to get the field list.
2. It skips the source-file search entirely (no Glob/Grep for this section).
3. It writes an index entry with `"source_files": []` and `"synthesized_from"` set to the parsed field list. The field names are dotted paths into the scan data (e.g., `project_model.tech_stack`). No validation of field paths at scan time — validation happens at write time if needed.
4. It MUST always produce the entry. The entry's presence is what triggers the writer's synthesis path. Without it, the writer finds no index match and either skips the section or generates from nothing.

Example index entry:
```json
"USER_GUIDE/overview": {
  "source_files": [],
  "synthesized_from": ["project_model.tech_stack", "project_model.entry_points", "project_model.components"],
  "staleness": "unknown"
}
```

Mark synthesized sections as non-optional in the template (no `<!-- OPTIONAL -->` marker).

**Merge behavior assumption:** Only the end-users audience scans USER_GUIDE sections, so synthesized entries won't collide with entries from other audience scans during `merge-scan.py` dedup. If shared_documents introduced overlapping keys in the future, the merge dedup strategy (keep the entry with more source_files) would discard the synthesized entry — but that's a future concern, not a Phase 4 blocker.

This keeps the dependency explicit at scan time. Synthesized sections use `sources: []` (empty) in their `docs-meta` marker — `staleness-check.py` treats empty sources as fresh by default (returns `None` at line 149-150), so no Python script changes are needed. Staleness tracking is inherently N/A for synthesized content: it's regenerated from the project model on every scan anyway.

**Scope additions for this:** `scan-audience.md` needs the SYNTHESIZED parsing rules above and explicit guidance to always produce an entry. `schema.md` needs `synthesized_from` as an optional string-array field on source_material_index entries. The writer's fallback logic needs one rule: "If `synthesized_from` is present and `source_files` is empty, generate from the named project model fields."

Each section also gets a `<!-- BOUNDARY: ... -->` comment specifying what belongs in end-user vs devops docs. Format: `<!-- BOUNDARY: Infrastructure setup belongs in devops/OPERATIONS.md, not here. -->` These serve as negative guidance for both the scan agent (don't index infrastructure files for this section) and the writer (don't generate infrastructure content here). Both agents need explicit handling added: the scan agent checks BOUNDARY before indexing source files; the writer checks BOUNDARY before generating content and cross-references the named alternate document instead.

### 4. Writer agent guidance — interface-aware, functional-first

- **Document through the primary interface.** Web dashboard → click paths. CLI → commands. Never default to CLI when the user's interface is a web UI.
- **Before any procedure, explain the goal.** What is the user trying to accomplish? Why?
- **After the goal, explain what the system will do.** Duration, what happens, what to expect.
- **Then the steps through the user's interface.**
- **Secondary interface as a tip.** "> **Power user tip:** You can also trigger this from the command line: `prefect deployment run ...`"
- **Expected results should be what the user sees.** For web: "The run appears in the dashboard with status 'Running'."
- **Cross-reference devops guide** for infrastructure setup, don't inline it.

### 5. Replacement template exemplars

The current exemplars in `USER_GUIDE.template.md` are entirely CLI-centric (`git clone`, `python3 main.py score`, etc.). The writer agent imitates exemplars directly ("Read the `<!-- EXAMPLE: ... -->` comment to understand what 'good' looks like"). Without new exemplars, the style won't change regardless of other fixes. These are the highest-leverage artifacts in this phase.

**Exemplars show web-UI style as the reference case** because it's the hardest to get right (click paths, screen states, UI elements) and the most common failure mode (defaulting to CLI). The exemplars are static — they don't change per-project. For CLI or API projects, the writer adapts the *structure* (goal-first, then steps, then expected results) to the detected interface type. Add explicit writer guidance: "Exemplars demonstrate web-UI style. If the primary interface is CLI or API, follow the same structure — functional context before procedure, expected results after steps — but use commands/responses instead of click paths."

**Getting Started — replacement exemplar:**

```markdown
<!-- EXAMPLE:
## Getting Started

Road Runner tracks your stock portfolio and scores companies using financial data.
Here's how to start using it.

### Open the dashboard

Go to **http://your-server:8080** in your browser. You'll see the main dashboard
with three panels: **Portfolio** (your tracked stocks), **Scores** (latest ratings),
and **Activity** (recent data updates).

### Add your first stock

1. Click **Add Stock** in the Portfolio panel.
2. Search for a company by name or ticker symbol.
3. Click the result to add it. The system queues a data pull — you'll see
   "Syncing..." next to the stock for a few minutes.
4. Once syncing completes, the stock appears with its current score.

### Understand the score

Each stock shows a score from 0–100. This combines financial health metrics
(debt ratio, cash flow, revenue trend) into a single number. Higher is better.
Click any stock to see the breakdown.

> **Power user tip:** You can also add stocks from the command line:
> `python3 main.py add AAPL`
-->
```

**Common Tasks — replacement exemplar:**

```markdown
<!-- EXAMPLE:
## Common Tasks

### Update quarterly financial data

After each quarter ends, you need to pull in the latest earnings reports, balance
sheets, and ownership filings for your tracked stocks. This typically takes
10–15 minutes depending on portfolio size.

1. In the dashboard, click **Data** in the top navigation.
2. Click **Run Quarterly Update**.
3. The progress bar shows which stocks are being updated.
4. When complete, the Activity panel on the home page shows "Quarterly update finished"
   with a timestamp.

If any stocks fail to update, they appear in red with an error message.
Click the stock to retry.

> **Power user tip:** `python3 main.py score --refresh` from the command line.

### Export portfolio report

To share your portfolio analysis with others or archive it:

1. Go to **Portfolio** → **Export** (top-right).
2. Choose format: PDF (for sharing) or CSV (for spreadsheets).
3. Select date range — defaults to current quarter.
4. Click **Download**. The file saves to your browser's download folder.

The PDF includes scores, score breakdowns, and trend charts for each stock.
The CSV includes raw data only.
-->
```

**Configuration — replacement exemplar:**

```markdown
<!-- EXAMPLE:
## Configuration

### User settings

Open **Settings** from the user menu (top-right corner). These settings affect
your experience — they don't change the system for other users.

| Setting | What it does | Default |
|---------|-------------|---------|
| Scoring model | Which financial model rates your stocks (Conservative, Balanced, Growth) | Balanced |
| Alert threshold | Score below this triggers an email alert | 40 |
| Portfolio visibility | Whether other users can see your portfolio | Private |

### Changing tracked stocks

Go to **Portfolio**, click the **gear icon** next to any stock to edit or remove it.
Changes take effect immediately — removed stocks are excluded from the next
quarterly update.
-->
```

**Troubleshooting — replacement exemplar:**

```markdown
<!-- EXAMPLE:
## Troubleshooting

### "No data found" on the dashboard

The portfolio panel shows "No data found" instead of your stocks.

**Likely cause:** The data feed hasn't completed its first sync yet, or a
scheduled update failed.

**What to do:**
1. Check the **Activity** panel on the home page. If you see "Sync in progress,"
   wait for it to finish (usually 5–10 minutes).
2. If Activity shows a failed update with a red timestamp, click **Data** →
   **Run Quarterly Update** to retry.
3. If the issue persists after a successful update, contact your system
   administrator — the data source may be unreachable.

### Scores show as "N/A"

A stock appears in your portfolio but its score shows "N/A" instead of a number.

**Likely cause:** Not enough financial data is available yet. New stocks need
at least one full quarter of data before scoring.

**What to do:**
1. Click the stock to open its detail page.
2. Check the **Data Coverage** section. It shows which quarters have data.
3. If coverage is partial, wait until the next quarterly update fills in
   the missing data. The score will appear automatically.
-->
```

### 6. Cross-audience boundary enforcement

- Installation and infrastructure setup → devops OPERATIONS.md
- API details and internal architecture → developer ARCHITECTURE.md
- System configuration → devops OPERATIONS.md
- User-facing configuration → stays in USER_GUIDE.md

---

## Scope

| Action | Files | Key changes |
|--------|-------|-------------|
| Edit | `auto-doc/references/templates/end-users/USER_GUIDE.template.md` | Restructure (add Overview/Concepts/Workflows with `<!-- SYNTHESIZED -->` comments), replace all exemplars with functional-first/interface-aware versions (see Section 5), add `<!-- BOUNDARY -->` comments, refine PURPOSE comments to scope for end-users |
| Edit | `auto-doc/agents/end-user-writer.md` | Add interface-aware Process step (read `user_interfaces`, branch on type), add `synthesized_from` fallback rule, add interface-aware conventions, add BOUNDARY comment handling |
| Edit | `auto-doc/agents/scan-audience.md` | Add per-audience exclusion/inclusion rules (end-user excludes: package manifests, migrations, systemd, CI, .env; includes: entry points, user config, workflows), add `<!-- SYNTHESIZED -->` comment handling, write `synthesized_from` index entries |
| Edit | `auto-doc/commands/auto-doc-scan.md` | Add `AskUserQuestion` to allowed-tools, add interface detection step with user confirmation, add config override priority chain |
| Edit | `auto-doc/references/schema.md` | Add `user_interfaces` to project model, add `synthesized_from` as optional field on source_material_index entries |
| Delete | `auto-doc/references/templates/end-users/DOMAIN_SPECIFIC.template.md` | Not needed — add back when a real use case requires it |

No Python script changes — `write-scan-output.py` validates key format only (`DOCUMENT/section-slug` pattern), not entry contents; fields like `synthesized_from` inside entries pass through unvalidated. `merge-scan.py` passes through `project_model` unchanged. Synthesized sections use `sources: []` in `docs-meta`, which `staleness-check.py` treats as fresh (returns `None` for empty sources).

---

## Decisions

1. **Projects where end-users ARE developers:** Not a configuration problem. If a project's users are developers, the user simply doesn't enable the `end-users` audience in `.docs.config.json` — the developer guide IS the user guide. The 4 existing audiences (end-users, developers, agents, devops) already cover the spectrum. No configurable profile needed.
2. **Synthesized section quality control:** Synthesized sections (Overview, Key Concepts, Workflows) generate purely from structured scan data fields — no source file reading, no LLM inference beyond what the fields contain. If `project_model` lacks enough data for a meaningful section (e.g., no components identified, no entry points found), the writer emits a `<!-- TODO: needs manual input — insufficient scan data for this section -->` placeholder rather than generating speculative content. This prevents hallucinated capabilities at the cost of sometimes producing thin sections the user must expand.
3. **Multi-interface projects:** USER_GUIDE documents through primary interface, mentions secondary as tips.
4. **DOMAIN_SPECIFIC.template.md:** Remove from v1.1 scope. Delete the template. Add back when a real use case requires it.
