# Shared Schema: findings.json

This is the contract between all three steps in the pipeline. The scanner creates it, the verifier enriches it, and the implementor updates it.

Each step adds its own fields — never overwrites another step's data. This creates a full audit trail.

## Structure

```json
{
  "project": "string — project name",
  "scan_date": "string — ISO 8601 timestamp",
  "root_path": "string — absolute path to project root",
  "summary": {
    "total_findings": 0,
    "by_severity": { "critical": 0, "high": 0, "medium": 0, "low": 0 },
    "by_category": { "orphaned-code": 0, "stale-code": 0, "...": 0 }
  },
  "findings": [
    {
      "id": "F001",
      "category": "orphaned-code | stale-code | dead-code-path | redundant-logic | unused-dependency | contract-drift | dangling-config | circular-dependency",
      "severity": "critical | high | medium | low",
      "confidence": "high | medium | low",
      "title": "Short human-readable description",
      "location": {
        "file": "relative/path/to/file.py",
        "lines": [10, 25],
        "symbol": "function_name or ClassName or null"
      },
      "evidence": "Why this was flagged — what the scanner observed.",
      "recommendation": "remove | refactor | update | merge | investigate",
      "notes": "Any caveats, e.g. 'may be used via dynamic dispatch'",

      "verification": null,
      "implementation": null
    }
  ]
}
```

## Fields Added by Verifier (step 2)

The verifier replaces the `"verification": null` field:

```json
"verification": {
  "safety": "safe-to-fix | needs-review | do-not-touch",
  "reasoning": "Why this classification was chosen.",
  "impact_analysis": "What changes when this finding is addressed.",
  "dependents": ["list", "of", "files/symbols", "that", "depend", "on", "this"],
  "test_coverage": "covered | partial | none",
  "proposed_change": "Precise description of what the implementor should do.",
  "risk_notes": "What could go wrong. Empty string if no risk.",
  "requires_human_approval": false
}
```

### Safety Classifications

| Classification | Meaning | Implementor behavior |
|---|---|---|
| `safe-to-fix` | Verifier confirmed this change has no downstream impact, or impact is fully covered by tests. | Implement automatically. |
| `needs-review` | Change is likely safe but has some uncertainty — dynamic dispatch, partial test coverage, or ambiguous impact. | Skip unless user explicitly approves. |
| `do-not-touch` | Verifier found the scanner was wrong (false positive), or the fix is too risky without major refactoring. | Never implement. Log reason and move on. |

## Fields Added by Implementor (step 3)

The implementor replaces the `"implementation": null` field:

```json
"implementation": {
  "status": "applied | skipped | failed | rolled-back",
  "change_description": "What was actually done.",
  "files_modified": ["relative/path/to/file.py"],
  "tests_run": true,
  "tests_passed": true,
  "rollback_commit": "git SHA or null",
  "failure_reason": "null or why it failed/was skipped"
}
```

## File Location Convention

All three steps read from and write to a shared workspace directory:

```
<project-root>/
├── .health-scan/                              ← workspace
│   ├── .health-ignore                         ← optional: gitignore-style exclusions
│   ├── .health-scan.config.json               ← optional: model & pipeline settings
│   ├── health-scan-findings.json              ← the shared contract
│   ├── health-scan-report.md                  ← human-readable scan report
│   ├── health-verify-report.md                ← human-readable verification report
│   ├── health-verify-test-baseline.json       ← test results before changes
│   ├── health-implement-report.md             ← human-readable implementation report
│   └── scan-logs/                             ← per-category scanner logs
│       ├── scan-orientation.md
│       ├── scan-orphaned-code.md / .json
│       ├── scan-stale-code.md / .json
│       └── ...
```

The scanner creates the workspace. The verifier and implementor expect it to exist.

## Configuration Files

### `.health-ignore`

Place in `.health-scan/` directory. Gitignore-style syntax for excluding files and directories from scanning.

```
# Directories to skip
node_modules
dist
build
.venv
vendor

# File patterns
*.min.js
*.generated.ts
```

**Default ignore patterns** (always applied even without a `.health-ignore` file):
`.git`, `node_modules`, `__pycache__`, `.health-scan`, `dist`, `build`, `.venv`, `venv`, `.mypy_cache`, `*.pyc`, `.tox`, `.eggs`, `*.egg-info`, `.next`, `.nuxt`, `coverage`, `.nyc_output`, `target`

### `.health-scan.config.json`

Place in `.health-scan/` directory. Controls pipeline behavior.

```json
{
  "scanner_model": "sonnet",
  "verifier_model": "sonnet"
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `scanner_model` | `"sonnet"` | Model for scanner subagents (Task tool `model` parameter). Options: `"sonnet"`, `"opus"`, `"haiku"`. |
| `verifier_model` | `"sonnet"` | Model for verifier subagents. |

## WIP State Files

Scanner subagents write work-in-progress state files to preserve progress in case of interruption.

**File pattern:** `.health-scan/scan-logs/scan-<category>-wip.json`

**States:**

```json
// In progress (written at start, updated periodically)
{
  "status": "in_progress",
  "files_checked": ["src/foo.py", "src/bar.py"],
  "findings_so_far": [
    { /* partial finding object */ }
  ]
}

// Completed (written when final output is ready)
{
  "status": "completed"
}
```

The scanner uses WIP files for retry logic: if a subagent fails before writing its final output, the scanner can re-spawn it with the partial results and a narrowed scope (only unchecked files).

Script-backed categories (circular-deps, unused-deps) do not use WIP files — their Python scripts are deterministic and fast.
