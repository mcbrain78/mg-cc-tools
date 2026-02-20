# Codebase Health Pipeline

A 3-command pipeline for safely auditing and cleaning up codebases, with special attention to agentic systems (LLM tools, agents, prompt management, orchestration).

## Installation

Use the install script to set up the commands. It copies command files and supporting resources, then resolves all internal file paths to absolute paths so the LLM can find them at runtime.

### Project-level (current project only)

```bash
# From the skill repo directory, run against your project root
cd /path/to/your/project
/path/to/code-health-skill/install.sh --project
```

This installs into `<project>/.claude/`.

### Global (all projects)

```bash
./install.sh --global
```

This installs into `~/.claude/`.

### Custom target

```bash
./install.sh --target /path/to/your/.claude
```

### What the installer does

1. Copies command files to `<target>/commands/mg/`.
2. Copies supporting files (scanner agents, schema, Python scripts) to `<target>/codebase-health/`.
3. Creates global default config at `<target>/codebase-health/references/.health-scan.config.json`.
4. Resolves all relative paths (`references/schema.md`, `{GLOBAL_CONFIG}`, `agents/*.md`, `{SCRIPTS_DIR}`) to absolute paths, so the LLM can find them at runtime.
5. Checks for `python3` availability and warns if not found.
6. (`--project` mode only) Creates `.health-scan/` in the project root with project-level `.health-scan.config.json` and an empty `.health-ignore`. Existing config files are preserved.

### Installed structure

```
<target>/                                    (your .claude/ directory)
├── commands/mg/
│   ├── codebase-health.md                   ← entry point (start here)
│   ├── codebase-health-scan.md              ← scanner command
│   ├── codebase-health-verify.md            ← verifier command
│   └── codebase-health-implement.md         ← implementor command
└── codebase-health/                         ← supporting files
    ├── agents/
    │   ├── TEMPLATE.md                      ← shared agent pattern
    │   ├── orphaned-code.md
    │   ├── stale-code.md
    │   ├── dead-code-paths.md
    │   ├── redundant-logic.md
    │   ├── unused-deps.md
    │   ├── contract-drift.md                ← specialized (highest-value for agentic)
    │   ├── dangling-config.md
    │   ├── circular-deps.md
    │   └── implementor.md                   ← subagent for batched implementation
    ├── references/
    │   └── schema.md                        ← shared data contract
    └── scripts/                             ← Python helper scripts
        ├── circular-deps.py                 ← deterministic cycle detection
        ├── unused-deps.py                   ← deterministic dependency analysis
        └── lib/                             ← shared Python library
            ├── __init__.py
            ├── ignore.py                    ← .health-ignore pattern handling
            └── imports.py                   ← multi-language import extraction
```

### Dependencies

- **Required:** `git` (for the implementor's commit-per-finding workflow)
- **Recommended:** `python3` 3.8+ (for fast, deterministic circular-deps and unused-deps scanning). Without Python, these scanners fall back to LLM-only analysis, which is slower and may exhaust context on large codebases.
- **No pip dependencies.** The Python scripts use only the standard library (`ast`, `fnmatch`, `json`, `pathlib`, `sys`).

---

## Configuration

### `.health-ignore` — Exclude directories and files

The installer creates an empty `.health-scan/.health-ignore` file when using `--project` mode. Add gitignore-style patterns to exclude directories or files from scanning:

```
# Heavy directories
node_modules
dist
build
vendor
.venv

# Generated files
*.min.js
*.generated.ts
*.pb.go

# Specific paths
legacy/
```

The scanner automatically merges your patterns with sensible defaults (`.git`, `node_modules`, `__pycache__`, etc.). The Python helper scripts also respect these patterns.

### `.health-scan.config.json` — Pipeline settings

The installer creates global default config in `<target>/codebase-health/references/.health-scan.config.json` for all install modes. For `--project` installs, it also creates a project-level copy at `<project>/.health-scan/.health-scan.config.json`.

**Config layering:** Project config overrides global defaults on a per-field basis. If a field is missing from the project config, the global value is used. To customize a single project, edit its `.health-scan/.health-scan.config.json`. To change defaults for all projects, edit the global config.

```json
{
  "scanner_model": "sonnet",
  "verifier_model": "sonnet",
  "implementer_model": "sonnet"
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `scanner_model` | `"sonnet"` | Model for scanner subagents. Options: `"sonnet"`, `"opus"`, `"haiku"`. |
| `verifier_model` | `"sonnet"` | Model for verifier subagents. |
| `implementer_model` | `"sonnet"` | Model for implementor subagents (used when work queue exceeds 10 findings). |

Using `"sonnet"` (the default) is recommended for scanning — it's sufficient for focused analysis work and much cheaper than opus. Use `"opus"` for projects where you need maximum accuracy on complex contract drift or subtle dead code patterns.

**Automatic batching:** When the implementor's work queue has more than 10 findings, it automatically switches to category-batched subagent mode. Each category is delegated to a subagent sequentially, with inter-batch test validation and rollback. This prevents context exhaustion on large finding sets while maintaining the safety guarantees (test after every change, one commit per finding). Below 10 findings, the implementor works inline as usual.

---

## Invoking the Commands

**Start here:**

```
/mg:codebase-health
```

This is the entry point. It checks where you are in the pipeline and tells you what to run next. If you've never run a scan, it explains the pipeline. If you're mid-way through, it picks up where you left off.

You can also invoke each step directly:

| Step | Command | What it does |
|---|---|---|
| Entry point | `/mg:codebase-health` | Checks pipeline state and guides you to the next step |
| 1. Scan | `/mg:codebase-health-scan` | Scans the codebase read-only and produces findings |
| 2. Verify | `/mg:codebase-health-verify` | Validates findings and classifies safety |
| 3. Implement | `/mg:codebase-health-implement` | Applies verified fixes with test-and-rollback |

You can also invoke them conversationally after the command prefix:

```
/mg:codebase-health-scan scan my project for health issues
/mg:codebase-health-verify verify the scan findings
/mg:codebase-health-implement apply the verified fixes, also approve F007 and F012
```

**Always run them in order.** Each command depends on the output of the previous one. The verifier will refuse to run without scanner output, and the implementor will refuse to run without verifier output.

---

## The Pipeline

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│  1. SCAN        │      │  2. VERIFY       │      │  3. IMPLEMENT       │
│                 │      │                  │      │                     │
│  Read-only.     │─────▶│  Read-only.      │─────▶│  Modifies code.     │
│  Finds issues.  │      │  Checks safety.  │      │  Tests each change. │
│  Writes report. │      │  Gates changes.  │      │  Commits per fix.   │
└─────────────────┘      └──────────────────┘      └─────────────────────┘
        │                        │                          │
   YOU REVIEW               YOU REVIEW                 YOU REVIEW
        │                        │                          │
        ▼                        ▼                          ▼
 health-scan-findings.json  (+ verification)          (+ implementation)
 health-scan-report.md      health-verify-report.md   health-implement-report.md
```

**You control the git workflow.** The pipeline never creates, switches, or manages branches. Set up your branch before running any command, and all commits land on the branch you have checked out.

---

## Safety Design

The pipeline is designed around one principle: **never break anything.**

- **Two read-only steps before any modification.** The scanner and verifier observe and report. Only the implementor writes to your codebase.
- **Human checkpoints between each step.** You review the scan report before verification. You review the verification report (and approve needs-review items) before implementation. The pipeline never barrels through without your sign-off.
- **Conservative classification.** The verifier defaults to `needs-review` when uncertain and `do-not-touch` when the finding might be a false positive. Only genuinely safe changes get the `safe-to-fix` label.
- **You own the branch.** Create a branch before running the implementor, or run it on your current branch — your call. The pipeline commits to wherever you are.
- **Continuous testing.** The verifier establishes a test baseline. The implementor runs tests after every single change and rolls back immediately on failure.
- **One commit per finding.** Each change is individually revertable with `git revert <SHA>`.
- **Structured audit trail.** `health-scan-findings.json` accumulates data from all three steps. You can trace any change back to its scan evidence, verification reasoning, and implementation status.

---

## Usage

### Step 1: Scan

```
/mg:codebase-health-scan scan my codebase for health issues
```

This produces (all inside `.health-scan/`):
- `health-scan-findings.json` — structured findings
- `health-scan-report.md` — human-readable report
- `scan-logs/` — per-category detail

**Review the report.** Understand what was found before proceeding.

### Step 2: Verify

```
/mg:codebase-health-verify verify the health scan findings
```

This produces:
- Updated `health-scan-findings.json` with verification data on each finding
- `health-verify-report.md`
- `health-verify-test-baseline.json` (if tests exist)

**Review the verification report.** Pay attention to:
- `needs-review` items — decide which to approve
- `do-not-touch` items — understand why the verifier rejected them
- The test baseline — is it clean?

### Step 3: Implement

First, set up your branch:
```bash
git checkout -b health-scan-cleanup
```

Then invoke the implementor:
```
/mg:codebase-health-implement apply the verified fixes
```

If you want to approve specific needs-review items, say so:
```
/mg:codebase-health-implement apply the verified fixes, also approve F007 and F012
```

This produces:
- One commit per applied finding on your current branch
- Updated `health-scan-findings.json` with implementation status
- `health-implement-report.md`

**Review the commits.** Revert individual changes with `git revert <SHA>` if needed.

---

## What Gets Scanned

| Category | What it finds |
|---|---|
| Orphaned Code | Completely unreachable code — nothing imports or calls it |
| Stale Code | Reachable but neglected — deprecated APIs, old patterns, stale TODOs |
| Dead Code Paths | Unreachable branches inside reachable functions |
| Redundant Logic | Duplicated code that should be shared |
| Unused Dependencies | Declared packages that nothing imports |
| Contract Drift | Tool schemas, descriptions, and agent prompts that don't match implementation |
| Dangling Config | Config entries nothing reads (or code reading undefined config) |
| Circular Dependencies | Module import cycles and tangled dependency graphs |

---

## Workspace Layout

All pipeline artifacts live in a single workspace directory:

```
your-project/
├── .health-scan/                              ← created by the scanner
│   ├── .health-ignore                         ← optional: gitignore-style exclusions
│   ├── .health-scan.config.json               ← optional: model & pipeline settings
│   ├── health-scan-findings.json              ← shared contract (enriched by each step)
│   ├── health-scan-report.md                  ← scanner's report
│   ├── health-verify-report.md                ← verifier's report
│   ├── health-verify-test-baseline.json       ← test results before changes
│   ├── health-implement-report.md             ← implementor's report
│   └── scan-logs/                             ← per-category scanner detail
│       ├── scan-orientation.md
│       ├── scan-orphaned-code.md / .json
│       ├── scan-contract-drift.md / .json
│       └── ...
```

Consider adding `.health-scan/` to your `.gitignore` if you don't want to track the workspace.

### WIP state and retry

Scanner subagents write work-in-progress (WIP) state files (`scan-<category>-wip.json`) as they work. If a subagent is interrupted (e.g., context window exhaustion), the scanner can re-spawn it with partial results and a narrowed scope. This means large codebases can be scanned reliably even when individual subagents hit limits.

The circular-deps and unused-deps categories use deterministic Python scripts instead of LLM analysis, so they don't need WIP/retry — they run fast and produce consistent results regardless of codebase size.

---

## Tips

- **Run the scan regularly** — monthly or after major refactors. Drift accumulates silently.
- **Contract drift is king** — for agentic systems, this is the single most valuable check. Tool schemas that don't match their implementation cause the LLM to misuse tools in subtle, hard-to-debug ways.
- **Don't skip verification** — the scanner uses heuristics and will have false positives. The verifier catches them. Skipping straight to implementation is how things break.
- **Start small** — on your first run, consider implementing only the `safe-to-fix` items and deferring `needs-review`. Build trust in the pipeline before approving riskier changes.
- **Use a dedicated branch** — while the commands don't manage branches for you, creating a `health-scan-cleanup` branch before running the implementor gives you a clean rollback path.
