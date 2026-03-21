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

The scan phase identifies the primary user interface as part of the project model:

- **Framework detection:** Flask/Django/FastAPI/Next.js → web app. Click/Typer/argparse → CLI. Prefect/Airflow → orchestration dashboard.
- **Config files:** `prefect.yaml` with deployments → Prefect dashboard is the UI.
- **Existing docs/README:** Often states "open the dashboard at..."
- **User-provided config:** `.docs.config.json` could include `"primary_interface": "web"` to override detection.

The project model in `docs-scan.json` would include:
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

### 2. Audience-aware source material filtering

The scan agent classifies source material by audience relevance. For end-users:

**Include:** Entry points, user-facing configuration, workflow/flow definitions, error messages, README.

**Exclude/deprioritize:** Package management, database migrations, system services, internal APIs, test infrastructure.

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

Each section gets a `<!-- BOUNDARY: ... -->` comment specifying what belongs in end-user vs devops docs.

### 4. Writer agent guidance — interface-aware, functional-first

- **Document through the primary interface.** Web dashboard → click paths. CLI → commands. Never default to CLI when the user's interface is a web UI.
- **Before any procedure, explain the goal.** What is the user trying to accomplish? Why?
- **After the goal, explain what the system will do.** Duration, what happens, what to expect.
- **Then the steps through the user's interface.**
- **Secondary interface as a tip.** "> **Power user tip:** You can also trigger this from the command line: `prefect deployment run ...`"
- **Expected results should be what the user sees.** For web: "The run appears in the dashboard with status 'Running'."
- **Cross-reference devops guide** for infrastructure setup, don't inline it.

### 5. Cross-audience boundary enforcement

- Installation and infrastructure setup → devops OPERATIONS.md
- API details and internal architecture → developer ARCHITECTURE.md
- System configuration → devops OPERATIONS.md
- User-facing configuration → stays in USER_GUIDE.md

---

## Scope

| Action | Files |
|--------|-------|
| Edit | `auto-doc/references/templates/end-users/USER_GUIDE.template.md` — restructure, add Overview/Concepts/Workflows, update exemplars |
| Edit | `auto-doc/agents/end-user-writer.md` — interface-aware writing, functional context, boundary enforcement |
| Edit | `auto-doc/agents/scan-audience.md` — interface detection, audience-aware relevance filtering |
| Edit | `auto-doc/commands/auto-doc-scan.md` — pass interface detection to scan agents |
| Edit | `auto-doc/references/schema.md` — add `user_interfaces` to project model |
| Delete | `auto-doc/references/templates/end-users/DOMAIN_SPECIFIC.template.md` — not needed, add back when a real use case requires it |

No Python script changes — this is a content quality improvement (templates, agents, LLM prompts).

---

## Decisions

1. **Projects where end-users ARE developers:** Not a configuration problem. If a project's users are developers, the user simply doesn't enable the `end-users` audience in `.docs.config.json` — the developer guide IS the user guide. The 4 existing audiences (end-users, developers, agents, devops) already cover the spectrum. No configurable profile needed.
2. **Overview section:** Generated draft from scan data — user can edit after.
3. **Multi-interface projects:** USER_GUIDE documents through primary interface, mentions secondary as tips.
4. **DOMAIN_SPECIFIC.template.md:** Remove from v1.1 scope. Delete the template. Add back when a real use case requires it.
