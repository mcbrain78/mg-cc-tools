# External Integrations

**Analysis Date:** 2026-03-15

## APIs & External Services

This project has **no direct API integrations**. mg-cc-tools is a collection of Claude Code slash commands that operate entirely on the local filesystem. The tools never make HTTP requests, connect to databases, or call external APIs.

However, tools generate prompts and task files that are consumed by Claude Code's LLM runtime, and some scanner scripts invoke external CLI tools as subprocesses.

## Claude Code Integration (Primary)

**Claude Code Slash Command System:**
- All tools install as `/mg:<tool-name>` slash commands into `.claude/commands/mg/`
- Command .md files contain YAML-style frontmatter (`name:`, `description:`, `allowed-tools:`) and LLM instruction prompts
- Commands are invoked within Claude Code sessions and have access to Claude Code tools (Bash, Read, Write, Edit, Glob, Grep, Task/Agent)
- The Task tool is used by complex commands (codebase-health, data-provider) to spawn subagent threads with specialized prompts

**Claude Code Hook System:**
- `permission-hooks/hooks/permission-guard.py` — A `PreToolUse` hook that intercepts Bash/Read/Edit/Write tool calls and checks for dangerous patterns (destructive git, secrets access, out-of-project paths). Returns `permissionDecision: "ask"` to trigger user approval prompts.
  - Hook receives JSON on stdin (tool_name, tool_input, cwd)
  - Hook emits JSON on stdout with hookSpecificOutput
  - Registered in `.claude/settings.json` under `hooks.PreToolUse`
- `cc-regression-test/hooks/intercept-trigger.py` — A test hook that intercepts specific Bash commands for regression testing of the hook system itself.

**Claude Code Settings:**
- `cc-regression-test/install.sh` programmatically merges hook entries into `.claude/settings.json` via inline Python
- `permission-hooks` provides a command (`/mg:install-permission-hooks`) that registers the hook after file installation

## Get Shit Done (GSD) Framework Integration

**Dependency:** Several tools require GSD to be installed in the target project.

**Tools that depend on GSD:**
- `debug-triage/` — Invokes `/gsd:debug`, `/gsd:add-phase` to triage bugs into GSD workflow
- `update-backlog/` — Invokes `/gsd:add-phase` to add items to GSD milestone backlog
- `new-milestone-gsd/` — Invokes `/gsd:new-milestone` to create new GSD milestones
- `mg-gsd-wrappers/` — Wraps `/gsd:discuss-phase`, `/gsd:plan-phase`, `/gsd:execute-phase` with deviation-aware enhancements
- `gsd-patches/` — Applies behavioral patches to installed GSD command files (modifies GSD's own `.claude/commands/gsd/*.md`)
- `create-context/` — Uses `.claude/get-shit-done/templates/context.md` to generate context documents

**GSD integration pattern:**
- GSD is installed at `.claude/get-shit-done/` with commands at `.claude/commands/gsd/`
- mg-cc-tools commands reference GSD slash commands by name (e.g., `/gsd:debug`)
- `gsd-patches/` reads patch definition .md files and applies them to GSD command files using text insertion/replacement
- `mg-gsd-wrappers/` adds pre/post processing around GSD commands (e.g., deviation tracking, methodology snapshots)

## External CLI Tool Integration (codebase-health scanners)

The codebase-health pipeline wraps external static analysis tools. These are invoked as subprocesses by Python scripts installed into the target project.

**vulture (Python dead code detection):**
- Integration: `codebase-health/scripts/vulture-scan.py`
- Method: Python API import (`from vulture import Vulture`)
- Install: `pip install vulture`
- Purpose: Cross-file unused function/class/import detection
- Output: JSON with unused code items, confidence scores, line ranges

**lizard (complexity analysis):**
- Integration: `codebase-health/scripts/lizard-scan.py`
- Method: Subprocess call with CSV output (`lizard <root> --csv -ENS`)
- Install: `pip install lizard`
- Purpose: Per-function NLOC, cyclomatic complexity, parameter count, nesting depth
- Output: JSON with functions exceeding thresholds and bloated files

**jscpd (copy-paste detection):**
- Integration: `codebase-health/scripts/jscpd-scan.py`
- Method: Subprocess call with JSON reporter (`jscpd <root> --reporters json`)
- Install: `npm install -g jscpd` or via `npx`
- Purpose: Token-level duplicate code block detection
- Output: JSON with clone pairs, line ranges, token counts

**pyright (type checking):**
- Integration: `codebase-health/scripts/pyright-scan.py`
- Method: Subprocess call with JSON output (`pyright --outputjson`)
- Install: `npm install -g pyright` or via `npx`
- Purpose: Dead code path detection (unreachable code) and contract drift (type mismatches)
- Output: JSON split into dead_code_paths and contract_drift buckets

**Tool detection pattern:** All scanner scripts use `shutil.which()` to locate the tool binary. If not found, they try `npx` (for Node tools) or `sys.executable -m` (for Python tools), then exit with a clear error message and install instructions.

## Data Storage

**Databases:**
- None — All data is stored as local JSON and Markdown files

**File Storage:**
- Local filesystem only
- Codebase-health pipeline: `.mg/health-scan/` directory in target project
  - `health-scan-findings.json` — Primary data contract (findings with verification and implementation status)
  - `scan-logs/` — Per-category scanner output files
  - WIP checkpoint files for crash recovery
- Data-provider pipeline: `.mg/data-provider/` directory in target project
  - `input/` — fields.yaml, providers.txt
  - `tasks/` — Per-(field, provider) markdown task files
  - `output/` — Generated coverage reports

**Caching:**
- None — No caching layer

## Authentication & Identity

**Auth Provider:**
- None — mg-cc-tools has no authentication. It runs within the user's Claude Code session which handles its own auth.

## Monitoring & Observability

**Error Tracking:**
- None — Errors are printed to stderr and scripts exit with non-zero codes

**Logs:**
- Scripts print progress summaries to stderr (e.g., "Found 15 unused code items", "Merged 42 findings from 8 categories")
- No structured logging framework
- No log files generated

## CI/CD & Deployment

**Hosting:**
- Git repository (local development, likely GitHub based on GSD references)
- No hosted deployment — tools are installed locally into target projects

**CI Pipeline:**
- Not detected in the repository (no `.github/workflows/`, no `.gitlab-ci.yml`)
- Tests run manually: `python3 -m pytest`
- Linting run manually: `ruff check .`

## Environment Configuration

**Required env vars:**
- None — No environment variables are required by any mg-cc-tools component

**Secrets location:**
- `.env` is in `.gitignore` but no code reads from it
- `permission-hooks/hooks/permission-guard.py` actively guards AGAINST secrets exposure (blocks access to `.env`, credential files, SSH keys, etc.)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Data Flow Contracts

**health-scan-findings.json (codebase-health pipeline):**
- Defined in `codebase-health/references/schema.md`
- Shared between scanner (step 1), verifier (step 2), and implementor (step 3)
- Each step adds fields to the same JSON structure without overwriting other steps' data
- Python scripts (`add-finding.py`, `merge-findings.py`, `verify-finding.py`, `update-findings.py`, `split-findings.py`) handle all JSON mutations with atomic writes (temp file + `os.replace()`)

**Task files (data-provider pipeline):**
- Markdown files with structured sections (Config, Research, Verification)
- Python scripts (`generate.py`, `status.py`, `summarize.py`) parse and update these files
- Parsed via regex-based section/key-value extraction (no YAML/TOML library)

## Inter-tool Dependencies

Tools are designed to be self-contained, but some have install-order dependencies:

| Tool | Depends on |
|------|-----------|
| `gsd-patches` | GSD installed in target project |
| `mg-gsd-wrappers` | GSD installed + `gsd-patches` recommended |
| `debug-triage` | GSD installed in target project |
| `update-backlog` | GSD installed in target project |
| `new-milestone-gsd` | GSD installed in target project |
| `create-context` | GSD installed in target project |
| `codebase-health` | vulture, lizard (pip); jscpd, pyright (npm) in target |
| `permission-hooks` | python3 in target |
| `data-provider` | python3 3.10+ in target |
| `cc-regression-test` | python3 in target |

---

*Integration audit: 2026-03-15*
