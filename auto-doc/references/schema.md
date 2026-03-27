# Shared Schema: docs-scan.json

This is the data contract for the `/mg:auto-doc` documentation pipeline. The scanner creates it, the generator reads it, and the verifier validates against it.

Each pipeline step reads its relevant fields and may enrich the document. The scan step populates all fields; the generate step reads but does not modify; the verify step adds quality metrics.

## Structure

```json
{
  "project": "string -- project name",
  "scan_date": "string -- ISO 8601 timestamp",
  "root_path": "string -- absolute path to project root",
  "mode": "initial | update",
  "last_generated": "string (ISO 8601) | null",
  "project_model": { "..." },
  "source_material_index": { "..." },
  "staleness_report": [ "..." ],
  "note_classifications": [ "..." ],
  "gap_analysis": { "..." },
  "gsd_context": { "..." }
}
```

## Top-Level Fields

### `project`

- **Type:** `string`
- **Required:** yes
- **Description:** Human-readable project name, derived from the repository directory name or a config override.
- **Example:** `"mg-cc-tools"`

### `scan_date`

- **Type:** `string` (ISO 8601)
- **Required:** yes
- **Description:** Timestamp when the scan was performed. UTC timezone.
- **Example:** `"2026-03-15T14:30:00Z"`

### `root_path`

- **Type:** `string`
- **Required:** yes
- **Description:** Absolute path to the project root directory that was scanned.
- **Example:** `"/home/user/projects/my-app"`

### `mode`

- **Type:** `string` (enum)
- **Required:** yes
- **Values:** `"initial"` | `"update"`
- **Description:** Whether this is a first-time scan (`initial`) or an incremental update (`update`). In update mode, the scanner reuses previous scan data and only re-scans changed areas.
- **Example:** `"initial"`

### `last_generated`

- **Type:** `string` (ISO 8601) | `null`
- **Required:** no (null or absent for initial scans; present after first generation)
- **Description:** ISO timestamp of when the generate command last ran. Written by the generate command at pipeline start. Used by the scan command to detect incremental mode and by diff-scan.py to scope changes. Over-inclusive by design: commits during generation appear in the next diff rather than being silently missed.
- **Example:** `"2026-03-22T14:30:00Z"`

## project_model

A structured representation of the project's architecture, technology stack, and components. Built by the scanner from source code analysis.

```json
"project_model": {
  "tech_stack": ["python", "bash", "markdown"],
  "entry_points": [
    {
      "path": "scripts/add-note.py",
      "type": "cli",
      "description": "Atomic append to notes inbox"
    }
  ],
  "components": [
    {
      "name": "json_io",
      "path": "scripts/lib/json_io.py",
      "purpose": "Atomic JSON load/save helpers",
      "public_api": ["load_json", "save_json"],
      "dependencies": ["json", "os"],
      "database_tables": []
    }
  ],
  "infrastructure": {
    "deployment": "npm package / bash install script",
    "ci": "none",
    "config_files": ["pyproject.toml", ".docs.config.json"]
  },
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

### `project_model.tech_stack`

- **Type:** `array of string`
- **Required:** yes
- **Description:** Detected technologies and languages used in the project.
- **Example:** `["python", "typescript", "react", "postgres"]`

### `project_model.entry_points`

- **Type:** `array of object`
- **Required:** yes
- **Description:** Files that serve as entry points to the project (CLI scripts, main modules, route handlers, etc.).

Each entry point object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | `string` | yes | Relative path from project root |
| `type` | `string` | yes | Entry point type: `"cli"`, `"api"`, `"web"`, `"worker"`, `"config"`, `"test"` |
| `description` | `string` | yes | What this entry point does |

### `project_model.components`

- **Type:** `array of object`
- **Required:** yes
- **Description:** Distinct modules, services, or logical units within the project.

Each component object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | yes | Component name (usually module or directory name) |
| `path` | `string` | yes | Relative path from project root |
| `purpose` | `string` | yes | What this component does |
| `public_api` | `array of string` | yes | Exported functions, classes, or endpoints |
| `dependencies` | `array of string` | yes | Other components or libraries this depends on |
| `database_tables` | `array of string` | yes | Database tables this component reads/writes (empty array if none) |

### `project_model.infrastructure`

- **Type:** `object`
- **Required:** yes
- **Description:** Deployment, CI, and configuration infrastructure.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `deployment` | `string` | yes | How the project is deployed |
| `ci` | `string` | yes | CI/CD system in use (or `"none"`) |
| `config_files` | `array of string` | yes | Configuration files in the project |

### `project_model.database`

- **Type:** `object or null`
- **Required:** yes
- **Description:** Database schema information extracted from ORM model definitions. `null` if the project has no database.

```json
"database": {
  "orm_framework": "SQLAlchemy 2.0",
  "migration_tool": "Alembic",
  "schemas": {
    "road_runner": {
      "tables": ["etl_runs", "stocks", "data_drift_warnings"],
      "migration_chain": "alembic_road_runner"
    },
    "raw_fmp": {
      "tables": ["raw_fmp_income_statements", "raw_fmp_balance_sheets"],
      "migration_chain": "alembic_road_runner"
    }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database.orm_framework` | `string` | yes | ORM framework name and version |
| `database.migration_tool` | `string` | yes | Migration tool (or `"none"`) |
| `database.schemas` | `object` | yes | Map of schema name to schema details |
| `database.schemas.{name}.tables` | `array of string` | yes | Tables in this schema |
| `database.schemas.{name}.migration_chain` | `string` | yes | Which migration chain manages this schema |

### `project_model.user_interfaces`

- **Type:** `array of object` (optional -- field may be absent)
- **Required:** no
- **Description:** Detected or configured user interface types for the project. When present, writer agents use this to adapt documentation style to the project's primary interface. When absent, writer agents fall back to CLI-style documentation.

Each user interface object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `string` | yes | Interface type: `"web"`, `"cli"`, `"api"` |
| `name` | `string` | yes | Human-readable interface name |
| `url_pattern` | `string or null` | yes | URL pattern for web interfaces, null for CLI/API |
| `primary` | `boolean` | yes | Whether this is the primary user interface |

Example:

```json
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
```

## source_material_index

Maps document sections to the source files they describe. Used by the staleness checker to determine which sections need updates when source files change.

```json
"source_material_index": {
  "USER_GUIDE/overview": {
    "source_files": [],
    "staleness": "unknown",
    "synthesized_from": ["project_model.components", "project_model.user_interfaces"]
  },
  "ARCHITECTURE/overview": {
    "source_files": ["src/app.ts", "src/routes/index.ts"],
    "staleness": "fresh"
  },
  "USER_GUIDE/getting-started": {
    "source_files": ["src/routes/dashboard.py", "src/cli/main.py"],
    "staleness": "stale"
  }
}
```

- **Type:** `object`
- **Required:** yes
- **Description:** Keys are `"document/section"` paths (e.g. `"ARCHITECTURE/overview"`). Values describe the source files backing that section.

Each value object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_files` | `array of string` | yes | Relative paths to source files that this section documents |
| `staleness` | `string` | yes | One of `"fresh"`, `"stale"`, `"unknown"`. Fresh means source files haven't changed since section was last generated. Stale means source files have changed. Unknown means no generation history exists. |
| `synthesized_from` | `array of string` | no | Dotted field paths into scan data (e.g., `"project_model.components"`). When present with empty `source_files`, signals the writer to generate from project model fields instead of source files. |

Optional field for synthesized sections (sections generated from project model fields instead of source files): when `synthesized_from` is present and `source_files` is empty, the writer generates content from the named project model fields rather than reading source files. This enables overview, concepts, and workflow sections that don't map to specific code files.

## staleness_report

Detailed report of sections that need attention because their underlying source material has changed.

```json
"staleness_report": [
  {
    "document": "ARCHITECTURE",
    "section": "database-layer",
    "reason": "Schema migration added new tables",
    "changed_files": ["prisma/schema.prisma", "src/db/migrations/003.sql"],
    "severity": "high",
    "suggested_action": "Regenerate section to document new User and Session tables"
  }
]
```

- **Type:** `array of object`
- **Required:** yes (empty array if nothing is stale)
- **Description:** Each entry identifies a document section that is out of date.

Each staleness entry:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document` | `string` | yes | Document name (e.g. `"ARCHITECTURE"`) |
| `section` | `string` | yes | Section identifier within the document |
| `reason` | `string` | yes | Human-readable explanation of why the section is stale |
| `changed_files` | `array of string` | yes | Source files that changed since last generation |
| `severity` | `string` | yes | One of `"high"`, `"medium"`, `"low"`. High = core functionality changed. Medium = supporting code changed. Low = minor changes (comments, formatting). |
| `suggested_action` | `string` | yes | What the generator should do to fix this section |

## note_classifications

**Deprecated.** This field is always an empty array going forward. Notes are now read directly from `notes-inbox.json` by the generate and update commands via `list-notes.py`. The scan step no longer classifies notes.

```json
"note_classifications": []
```

- **Type:** `array of object`
- **Required:** yes (always empty array)
- **Description:** Previously mapped notes to their target documentation locations. Now deprecated -- notes are read directly from the inbox by generate and update commands.

Each classification entry:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `note_id` | `string` | yes | Reference to the note in `notes-inbox.json` (format: `NOTE-NNN`) |
| `audience` | `string` | yes | Target audience: `"end-users"`, `"developers"`, `"agents"`, `"devops"` |
| `document` | `string` | yes | Target document name (e.g. `"ARCHITECTURE"`) |
| `section` | `string` | yes | Target section within the document |
| `confidence` | `number` | yes | Classification confidence, 0.0 to 1.0. Below 0.5 should be flagged for human review. |

## gap_analysis

Identifies components and topics that lack documentation coverage.

```json
"gap_analysis": {
  "undocumented_components": ["scripts/lib/git_helpers.py", "agents/scanner.md"],
  "missing_for_audience": {
    "end-users": ["installation", "getting-started"],
    "developers": ["api-reference"],
    "agents": [],
    "devops": ["deployment", "monitoring"]
  }
}
```

- **Type:** `object`
- **Required:** yes

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `undocumented_components` | `array of string` | yes | Components from `project_model.components` that have no corresponding documentation section |
| `missing_for_audience` | `object` | yes | Per-audience list of topics that should be documented but aren't. Keys are audience names, values are arrays of missing topic strings. |

## gsd_context

Integration with the Get Shit Done workflow. Captures milestone progress and deviations that should be reflected in documentation. Null if GSD is not installed or `gsd_integration` is disabled in config.

```json
"gsd_context": {
  "milestone": "v1.0",
  "completed_phases": ["01-foundation", "02-templates"],
  "deviations": [
    "Switched from REST to GraphQL in phase 03"
  ],
  "new_requirements_completed": ["AUTH-01", "AUTH-02", "API-05"]
}
```

- **Type:** `object | null`
- **Required:** no (null when GSD integration is disabled)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `milestone` | `string` | yes | Current GSD milestone identifier |
| `completed_phases` | `array of string` | yes | List of completed phase identifiers |
| `deviations` | `array of string` | yes | Plan deviations that affect documentation |
| `new_requirements_completed` | `array of string` | yes | Requirement IDs completed since last doc generation |

## Complete Minimal Example

A minimal valid `docs-scan.json` for an initial scan of a small project:

```json
{
  "project": "my-app",
  "scan_date": "2026-03-15T14:30:00Z",
  "root_path": "/home/user/projects/my-app",
  "mode": "initial",
  "last_generated": null,
  "project_model": {
    "tech_stack": ["python"],
    "entry_points": [
      {
        "path": "main.py",
        "type": "cli",
        "description": "Application entry point"
      }
    ],
    "components": [
      {
        "name": "core",
        "path": "src/core.py",
        "purpose": "Core business logic",
        "public_api": ["process", "validate"],
        "dependencies": [],
        "database_tables": []
      }
    ],
    "infrastructure": {
      "deployment": "pip install",
      "ci": "none",
      "config_files": ["pyproject.toml"]
    },
    "user_interfaces": [],
    "database": null
  },
  "source_material_index": {},
  "staleness_report": [],
  "note_classifications": [],
  "gap_analysis": {
    "undocumented_components": ["src/core.py"],
    "missing_for_audience": {
      "end-users": ["installation", "usage"],
      "developers": ["architecture", "api-reference"],
      "agents": ["system-map"],
      "devops": ["deployment"]
    }
  },
  "gsd_context": null
}
```

## Verify Findings: docs-verify-findings.json

A flat array of verification findings produced by the verifier agent during the verify pipeline step. Each finding represents a single quality issue in a specific document section.

**Location:** `.mg/docs/docs-verify-findings.json`

**Lifecycle:**
- Created/cleared by `auto-doc-verify.md` before each verify run
- Populated by the verifier agent via `add-verify-finding.py` (one call per finding)
- Read by `auto-doc-generate.md` via `list-verify-findings.py` for the 3rd approval tier
- Cleared again on the next verify run (findings from skipped approvals reappear naturally)

### Structure

```json
[
  {
    "document": "string -- document name matching config, without .md extension (e.g., OPERATIONS)",
    "section": "string -- section slug (e.g., deployment-pipeline)",
    "audience": "string -- audience key (e.g., devops)",
    "severity": "string -- critical | high | medium | low | info",
    "check": "string -- which check found this (see valid values below)",
    "description": "string -- what is wrong",
    "suggestion": "string -- how to fix it",
    "group_id": "string -- computed: document/section (e.g., OPERATIONS/deployment-pipeline)"
  }
]
```

### Required Fields

All 7 input fields are required per finding. The `add-verify-finding.py` script validates these before appending and computes `group_id` automatically (8 fields total in output).

| Field | Type | Valid Values | Description |
|-------|------|-------------|-------------|
| `document` | `string` | Any document name from config (without `.md` extension) | Document where the issue was found. `.md` extension is stripped automatically. |
| `section` | `string` | Section slug | Section within the document |
| `audience` | `string` | Audience key | Target audience for the document |
| `severity` | `string` | `critical`, `high`, `medium`, `low`, `info` | Impact level of the issue |
| `check` | `string` | See valid check types below | Which verification check found this |
| `description` | `string` | Free text | What is wrong |
| `suggestion` | `string` | Free text | How to fix it |
| `group_id` | `string` | Computed: `{document}/{section}` | Groups related findings about the same document section. Added automatically by `add-verify-finding.py`. |

### Valid Check Types

**Mechanical checks (6):** `reference-integrity`, `cross-doc`, `diataxis`, `completeness`, `example-validity`, `link-integrity`

**Editorial checks — universal (8):** `filler-content`, `heading-content-mismatch`, `inconsistent-granularity`, `dangling-prose-reference`, `unexplained-code-block`, `internal-contradiction`, `malformed-table`, `placeholder-content`

**Editorial checks — end-user (4):** `end-user-jargon`, `end-user-missing-expected-result`, `end-user-implementation-leak`, `end-user-missing-goal`

**Editorial checks — developer (3):** `developer-abstract-architecture`, `developer-missing-types`, `developer-adr-missing-alternatives`

**Editorial checks — agent (3):** `agent-ambiguous-constraint`, `agent-missing-negative-examples`, `agent-missing-consequences`

**Editorial checks — devops (3):** `devops-missing-expected-output`, `devops-missing-rollback`, `devops-placeholder-in-command`

**Editorial checks — shared (1):** `overview-missing-audience`

### Example

```json
[
  {
    "document": "OPERATIONS",
    "section": "deployment-pipeline",
    "audience": "devops",
    "severity": "high",
    "check": "reference-integrity",
    "description": "File path src/deploy/old-pipeline.sh referenced in section does not exist",
    "suggestion": "Update reference to src/deploy/pipeline.sh (renamed in commit abc1234)",
    "group_id": "OPERATIONS/deployment-pipeline"
  },
  {
    "document": "ARCHITECTURE",
    "section": "data-model",
    "audience": "developers",
    "severity": "medium",
    "check": "diataxis",
    "description": "Reference section contains step-by-step tutorial instructions (lines 45-62)",
    "suggestion": "Move procedural content to DEVELOPER_GUIDE/database-setup how-to section",
    "group_id": "ARCHITECTURE/data-model"
  }
]
```

## Diff Scope: diff-scope.json

A scoped work order produced by `diff-scan.py` for incremental scans. Contains the set of documentation sections affected by code changes since the last generation, along with new file candidates and deleted file references.

**Location:** `.mg/docs/diff-scope.json` (NOT `scan-logs/` -- avoids being picked up by `merge-scan.py` which reads all `*.json` in `scan-logs/`)

**Lifecycle:**
- Created by the scan command in incremental mode via `diff-scan.py`
- Read by scan agents to scope their analysis to affected sections only
- Deleted on the next scan run (scan-logs cleanup does not affect this file, but the next scan overwrites it)

### Structure

```json
{
  "since": "string -- ISO 8601 timestamp used as diff baseline",
  "summary": {
    "files_changed": "number -- total files modified",
    "files_added": "number -- new files not in any manifest",
    "files_deleted": "number -- files deleted but still in manifests",
    "sections_affected": "number -- total documentation sections needing update",
    "new_file_candidates": "number -- files to be classified by scan agents"
  },
  "affected_sections": [
    {
      "audience": "string -- audience key (e.g., developers)",
      "document": "string -- document name (e.g., ARCHITECTURE)",
      "section": "string -- section slug (e.g., system-overview)",
      "reason": "string -- why this section is affected (e.g., source file modified)",
      "changed_files": ["array of string -- files that changed for this section"],
      "gsd_context": "string | null -- GSD phase context explaining the change",
      "renames": "object | null -- optional mapping of old_path -> new_path for renamed files"
    }
  ],
  "new_file_candidates": [
    {
      "file": "string -- relative path to new file",
      "reason": "string -- why this is a candidate (e.g., new file, not in any manifest)",
      "gsd_context": "string | null -- GSD phase context if available"
    }
  ],
  "deleted_files": [
    {
      "file": "string -- relative path to deleted file",
      "referenced_in": [
        {
          "audience": "string -- audience key",
          "document": "string -- document name",
          "section": "string -- section slug"
        }
      ]
    }
  ],
  "gsd_phases_since": [
    {
      "phase": "string -- phase number (e.g., 06)",
      "name": "string -- phase name (e.g., fix-verify-feedback-loop)",
      "deviations": ["array of string -- plan deviations"],
      "key_decisions": ["array of string -- key decisions made"]
    }
  ]
}
```

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `since` | `string` (ISO 8601) | yes | Timestamp used as the diff baseline (from `last_generated` in docs-scan.json) |
| `summary` | `object` | yes | Aggregate counts for display |
| `affected_sections` | `array of object` | yes | Sections needing re-analysis (one entry per audience x document x section) |
| `new_file_candidates` | `array of object` | yes | Files not in any manifest, to be classified by scan agents |
| `deleted_files` | `array of object` | yes | Files still in manifests but deleted from the filesystem |
| `gsd_phases_since` | `array of object` | yes | GSD phases modified since last generation (empty if GSD not available) |

### Example

```json
{
  "since": "2026-03-17T14:30:00Z",
  "summary": {
    "files_changed": 15,
    "files_added": 3,
    "files_deleted": 1,
    "sections_affected": 8,
    "new_file_candidates": 3
  },
  "affected_sections": [
    {
      "audience": "developers",
      "document": "ARCHITECTURE",
      "section": "system-architecture",
      "reason": "source file modified",
      "changed_files": ["src/llm/model_routing.py"],
      "gsd_context": "Phase 6: replaced route_model() with provider-specific functions",
      "renames": {"src/old/model.py": "src/llm/model_routing.py"}
    }
  ],
  "new_file_candidates": [
    {
      "file": "src/verify/add-verify-finding.py",
      "reason": "new file, not in any manifest",
      "gsd_context": null
    }
  ],
  "deleted_files": [
    {
      "file": "src/old/legacy.py",
      "referenced_in": [
        {"audience": "developers", "document": "ARCHITECTURE", "section": "data-model"}
      ]
    }
  ],
  "gsd_phases_since": [
    {
      "phase": "06",
      "name": "fix-verify-feedback-loop",
      "deviations": [],
      "key_decisions": ["replaced route_model with provider-specific functions"]
    }
  ]
}
```

## File Location Convention

The scan output and related pipeline files live in the project workspace:

```
<project-root>/
├── .mg/
│   └── docs/
│       ├── .docs.config.json        -- project config overrides
│       ├── notes-inbox.json          -- captured documentation notes
│       ├── docs-scan.json            -- the shared scan contract
│       ├── docs-verify-findings.json -- structured verify findings (flat array)
│       ├── diff-scope.json           -- scoped work order for incremental scans
│       ├── docs-update-report.md     -- generation report
│       ├── docs-verify-report.md     -- verification report
│       └── scan-logs/                -- per-audience scan intermediates
```

The scanner creates the workspace and `docs-scan.json`. The generator and verifier expect them to exist.

## Reference Manifests

Reference manifests track which code symbols and file paths each document section references. They are produced by the generate pipeline and consumed by the verify pipeline for reference-integrity checks.

### Location

```
<project-root>/.mg/docs/reference-manifests/{audience}.json
```

One file per audience: `developers.json`, `end-users.json`, `agents.json`, `devops.json`.

### Structure

```json
{
  "audience": "string -- audience key (e.g., developers)",
  "generated": "string -- ISO 8601 timestamp of last generation",
  "documents": {
    "DOCUMENT_NAME": {
      "section-slug": {
        "symbols": ["array of string -- unqualified code identifiers"],
        "file_paths": ["array of string -- files/directories relative to project root"]
      }
    }
  }
}
```

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audience` | `string` | yes | Audience key: `"developers"`, `"end-users"`, `"agents"`, `"devops"` |
| `generated` | `string` (ISO 8601) | yes | Timestamp of last generation run |
| `documents` | `object` | yes | Nested object keyed by document name, then section slug |

### Section Entry Fields

Each section entry within a document:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbols` | `array of string` | yes | Unqualified code identifiers (function names, class names, constants). Never dotted paths -- `load_json` not `lib.json_io.load_json`. |
| `file_paths` | `array of string` | yes | Files and directories referenced, relative to project root. |
| `calls` | `array of object` | no | Function calls used in doc examples. Each: `{"symbol": "name", "kwargs": ["param1", "param2"]}`. Verified by `verify-references.py` against actual function signatures via `ast.parse()`. |

### Upsert Key

Entries are upserted by `(document, section)` pair. Writing the same document and section replaces the previous entry rather than creating duplicates.

### Lifecycle

- **Initial mode:** All manifest files are cleared before a full generation run. Writer agents call `add-manifest-entry.py` after writing each section.
- **Update mode:** Only regenerated sections are upserted. Sections not regenerated preserve their existing manifest entries.
- **Verify consumption:** The verify pipeline reads manifests to check that referenced symbols and file paths still exist in the codebase.

### `_written_sections` Metadata

A transient metadata entry used for stale section cleanup during generation:

```json
{
  "document": "ARCHITECTURE",
  "section": "_written_sections",
  "symbols": [],
  "file_paths": [],
  "sections_written": ["overview", "data-model", "auth-flow"]
}
```

The `_written_sections` entry bypasses the normal validation that requires at least one non-empty `symbols` or `file_paths` array. It requires a `sections_written` field instead. This entry is stripped before the manifest is persisted for verify consumption.

### Complete Example

A minimal manifest for the `developers` audience with two documents:

```json
{
  "audience": "developers",
  "generated": "2026-03-22T14:30:00Z",
  "documents": {
    "ARCHITECTURE": {
      "overview": {
        "symbols": ["App", "Router", "middleware"],
        "file_paths": ["src/app.ts", "src/routes/index.ts"]
      },
      "data-model": {
        "symbols": ["User", "Session", "Product"],
        "file_paths": ["prisma/schema.prisma", "src/db/migrations/"]
      }
    },
    "API_REFERENCE": {
      "authentication": {
        "symbols": ["login", "logout", "refresh_token"],
        "file_paths": ["src/api/auth/login.ts", "src/api/auth/logout.ts"]
      },
      "user-endpoints": {
        "symbols": ["get_user", "update_profile", "delete_account"],
        "file_paths": ["src/api/users/routes.ts"]
      }
    }
  }
}
```
