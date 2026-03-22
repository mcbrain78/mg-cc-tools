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
  }
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

## source_material_index

Maps document sections to the source files they describe. Used by the staleness checker to determine which sections need updates when source files change.

```json
"source_material_index": {
  "ARCHITECTURE/overview": {
    "source_files": ["src/app.ts", "src/routes/index.ts"],
    "staleness": "fresh"
  },
  "USER_GUIDE/installation": {
    "source_files": ["package.json", "install.sh"],
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

Notes captured via `/mg:auto-doc-add` that have been classified by audience, document, and section.

```json
"note_classifications": [
  {
    "note_id": "NOTE-001",
    "audience": "developers",
    "document": "ARCHITECTURE",
    "section": "auth-flow",
    "confidence": 0.85
  }
]
```

- **Type:** `array of object`
- **Required:** yes (empty array if no notes)
- **Description:** Each entry maps a note to its target location in the documentation.

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
    }
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
    "document": "string -- document name matching config (e.g., OPERATIONS)",
    "section": "string -- section slug (e.g., deployment-pipeline)",
    "audience": "string -- audience key (e.g., devops)",
    "severity": "string -- critical | high | medium | low | info",
    "check": "string -- which check found this (reference-integrity | cross-doc | diataxis | completeness | example-validity | link-integrity)",
    "description": "string -- what is wrong",
    "suggestion": "string -- how to fix it"
  }
]
```

### Required Fields

All 7 fields are required per finding. The `add-verify-finding.py` script validates these before appending.

| Field | Type | Valid Values | Description |
|-------|------|-------------|-------------|
| `document` | `string` | Any document name from config | Document where the issue was found |
| `section` | `string` | Section slug | Section within the document |
| `audience` | `string` | Audience key | Target audience for the document |
| `severity` | `string` | `critical`, `high`, `medium`, `low`, `info` | Impact level of the issue |
| `check` | `string` | `reference-integrity`, `cross-doc`, `diataxis`, `completeness`, `example-validity`, `link-integrity` | Which verification check found this |
| `description` | `string` | Free text | What is wrong |
| `suggestion` | `string` | Free text | How to fix it |

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
    "suggestion": "Update reference to src/deploy/pipeline.sh (renamed in commit abc1234)"
  },
  {
    "document": "ARCHITECTURE",
    "section": "data-model",
    "audience": "developers",
    "severity": "medium",
    "check": "diataxis",
    "description": "Reference section contains step-by-step tutorial instructions (lines 45-62)",
    "suggestion": "Move procedural content to DEVELOPER_GUIDE/database-setup how-to section"
  }
]
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
