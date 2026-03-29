# Phase 1: Foundation & Infrastructure

> Source: docs/work-queue/todo/doc-command/DESIGN.md
> Phase goal: All supporting infrastructure exists so pipeline steps and commands can be built on top of them
> Requirements: INF-01, INF-02, INF-03, INF-04, INF-05, INF-06, INF-07, INF-08, INF-09, INF-10

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

*(consumed by Phase 3, 4, 5)*

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

## Inbox Schema

*(consumed by Phase 5 — `/mg:add-docs` command)*

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

---

## Tool Workspace (gitignored or project-local)

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

## Tool Source Directory Structure (scripts and references)

```
docs/
├── install.sh
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
    └── .docs.config.json           ← Global default configuration
```

[See Phase 2 for templates/ and agents/ directory structure]

---

## Open Items (Phase 1)

2. **Schema definition** — Full `docs-scan.json` schema in `references/schema.md` (JSON Schema or structured markdown like codebase-health).
3. **Style guide** — Cross-audience writing conventions document for `references/style-guide.md`.

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
- Install script with sed replacements: `codebase-health/install.sh`
- Atomic JSON I/O scripts: `codebase-health/scripts/add-finding.py`
- Schema definition format: `codebase-health/references/schema.md`
- Config layering logic: `codebase-health/commands/codebase-health-scan.md` (config merge section)

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
*Phase: 01-foundation-infrastructure*
*Date: 2026-03-16*
