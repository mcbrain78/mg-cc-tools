# Phase 6: Fix Verify Feedback Loop and Scan Output - Research

**Researched:** 2026-03-17
**Domain:** Python script I/O patterns, LLM agent workflow design, multi-tier approval UX
**Confidence:** HIGH

## Summary

Phase 6 fixes two independent problems in the `/mg:docs` pipeline. Part A closes the broken verify-generate feedback loop so verify findings flow back into generate as a 3rd approval tier. Part B replaces direct LLM JSON writes in scan agents with a validation script (`write-scan-output.py`). Both follow the project's established principle: LLMs do analysis, Python scripts do serialization.

The codebase already contains all the patterns needed. `codebase-health/scripts/add-finding.py` is the direct precedent for the per-finding append pattern (Part A). `create-docs/scripts/lib/json_io.py` provides atomic JSON I/O used by all existing scripts. The file-based I/O pattern (`--input`/`--output` via temp files) is specified in the CONTEXT.md decisions and addresses the latent shell metacharacter escaping bug.

**Primary recommendation:** Implement Part A first (scripts + tests, then agent/command changes) since it fixes the user-facing problem. Part B is independent hardening that can follow immediately after.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Parts A and B are independent work streams with no dependency between them
- Part A (verify feedback loop) is the priority
- Verify findings are a flat array in `docs-verify-findings.json` stored in `.mg/docs/`
- One entry per document/section/issue with 7 required fields: `document`, `section`, `audience`, `severity`, `check`, `description`, `suggestion`
- Verifier agent uses two-step workflow: Step 1 (per-finding, calls `add-verify-finding.py`), Step 2 (report generation, reads accumulated findings via `list-verify-findings.py`)
- Generate and writer agents never read `docs-verify-findings.json` directly -- they use filter scripts (`list-verify-findings.py`) that write output to temp files
- Generate approval flow has 3 tiers: staleness -> verify findings -> notes
- Findings alone prevent early exit
- Uniform 4-option approval (approve all / by document / by severity / cancel) across all 3 tiers in a single decision point
- Merged drill-in: when user picks "by document", show staleness + findings together
- Writer agents receive approved verify findings via `list-verify-findings.py --document X --audience Y --output`
- Verify command clears `docs-verify-findings.json` before each run
- No fixability classification -- all findings presented, user decides
- File-based I/O: all data through files, never through shell boundaries (`--input`/`--output`)
- Strict validation, graceful degradation: invalid input rejected to `.rejected` file, pipeline continues
- Script handles all formatting: agent provides values, script handles JSON structure and atomic writes
- `write-scan-output.py` validates `source_material_index`, `gap_analysis`, correct key format `DOCUMENT/section-slug`
- Scan agents produce complete output per audience (one validation call per audience, not per-finding)
- Rewrite `verifier.md` directly -- old workflow is obsolete
- Bake LSP symbol verification and glossary reconciliation into agent definition (eliminate all Task prompt overrides)
- Script paths passed as input parameters to verifier agent
- Router gets findings-aware state after verify report check
- Simple file check for router: reads `docs-verify-findings.json` directly, checks if array non-empty

### Implementation Scope -- Part A Files
- `create-docs/scripts/add-verify-finding.py` -- New
- `create-docs/scripts/list-verify-findings.py` -- New
- `create-docs/scripts/tests/test_add_verify_finding.py` -- New
- `create-docs/scripts/tests/test_list_verify_findings.py` -- New
- `create-docs/agents/verifier.md` -- Full rewrite
- `create-docs/commands/create-docs-generate.md` -- Add 3rd approval tier
- `create-docs/commands/create-docs-verify.md` -- Simplify
- `create-docs/commands/create-docs.md` -- Add findings-aware state
- `create-docs/references/schema.md` -- Document verify findings format
- `create-docs/install.sh` -- Add scripts

### Implementation Scope -- Part B Files
- `create-docs/scripts/write-scan-output.py` -- New
- `create-docs/scripts/tests/test_write_scan_output.py` -- New
- `create-docs/agents/scan-audience.md` -- Update Output section
- `create-docs/commands/create-docs-scan.md` -- Update agent spawn
- `create-docs/install.sh` -- Add script

### Claude's Discretion
- Internal structure of `add-verify-finding.py` and `list-verify-findings.py` (argparse patterns, error handling style)
- How to split Part A into plans (scripts+tests first vs agent changes first vs all together)
- Whether to sequence Part A and Part B or parallelize them
- Test fixtures and test organization
- Exact approval flow UX wording (Level 1 overview formatting, drill-in presentation)
- How `write-scan-output.py` handles backwards compatibility with existing LLM-written scan-logs

### Deferred Ideas (OUT OF SCOPE)
- Shell metacharacter fix in `codebase-health/scripts/add-finding.py` -- filed as separate todo

</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3.8+ stdlib | 3.8+ | All script logic | Zero external dependencies -- project constraint |
| `argparse` | stdlib | CLI argument parsing | Used by all existing scripts (add-note.py, add-finding.py, merge-scan.py, etc.) |
| `json` | stdlib | JSON serialization/deserialization | Standard for all JSON I/O in this project |
| `os` / `os.path` | stdlib | File operations, path manipulation | Atomic writes via `os.replace` pattern |
| `tempfile` | stdlib | Temp file creation in tests | Used in all existing test suites |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lib/json_io.py` | internal | `load_json()` / `save_json()` with atomic writes | All new scripts MUST use this for JSON I/O (established pattern) |
| `pytest` | dev dependency | Test framework | All test files, invoked via `python3 -m pytest` |
| `subprocess` | stdlib | Script invocation in tests | For testing CLI interface (--input/--output args) |
| `importlib` | stdlib | Import kebab-case modules in tests | For testing internal functions directly |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `lib/json_io.py` | Direct `json.dump` + `os.replace` | json_io.py already handles makedirs + atomic pattern; duplication is unnecessary |
| `argparse` | Click/Typer | External dependency violates zero-dependency constraint |

## Architecture Patterns

### Recommended Project Structure (new files)
```
create-docs/
├── scripts/
│   ├── add-verify-finding.py      # Part A: append finding to consolidated file
│   ├── list-verify-findings.py    # Part A: filter/query findings
│   ├── write-scan-output.py       # Part B: validate + write scan output
│   └── tests/
│       ├── test_add_verify_finding.py
│       ├── test_list_verify_findings.py
│       └── test_write_scan_output.py
├── agents/
│   ├── verifier.md                # Full rewrite
│   └── scan-audience.md           # Output section update
├── commands/
│   ├── create-docs-generate.md    # Add 3rd approval tier
│   ├── create-docs-verify.md      # Simplify (remove overrides)
│   ├── create-docs.md             # Add findings-aware state
│   └── create-docs-scan.md        # Pass script path to scan agents
├── references/
│   └── schema.md                  # Add verify findings JSON schema
└── install.sh                     # Add 3 new scripts
```

### Pattern 1: File-Based I/O (--input / --output)
**What:** Agent writes data to temp file via Write tool, calls script with `--input /tmp/data.json`, script validates and writes to destination. For reads, script writes to `--output /tmp/results.json`, agent reads via Read tool.
**When to use:** All new scripts in Phase 6. Replaces the CLI-args pattern used by `codebase-health/scripts/add-finding.py`.
**Example:**
```python
# Agent workflow (in agent .md instructions):
# 1. Agent writes finding data to temp file via Write tool
# 2. Agent calls: python3 add-verify-finding.py --input /tmp/finding.json --findings-file .mg/docs/docs-verify-findings.json
# 3. Script reads --input, validates, appends to --findings-file

# Script pattern:
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

REQUIRED_FIELDS = ["document", "section", "audience", "severity", "check", "description", "suggestion"]
VALID_SEVERITIES = ["critical", "high", "medium", "low", "info"]
VALID_CHECKS = ["reference-integrity", "cross-doc", "diataxis", "completeness", "example-validity", "link-integrity"]

def validate_finding(finding):
    """Validate a single finding dict. Returns (is_valid, error_message)."""
    for field in REQUIRED_FIELDS:
        if field not in finding:
            return False, f"Missing required field: {field}"
    if finding["severity"] not in VALID_SEVERITIES:
        return False, f"Invalid severity: {finding['severity']}"
    if finding["check"] not in VALID_CHECKS:
        return False, f"Invalid check type: {finding['check']}"
    return True, None
```

### Pattern 2: Per-Finding Append (add-verify-finding.py)
**What:** Script reads input JSON from `--input` temp file, validates required fields, appends to a flat array file. Follows the same principle as `codebase-health/scripts/add-finding.py` but with file-based input instead of CLI args.
**When to use:** When the verifier agent discovers an issue during any of its 6 checks.
**Example:**
```python
# Precedent: codebase-health/scripts/add-finding.py (lines 51-71)
# Same load_array -> append -> save_array pattern
# Key difference: input comes from --input file, not --category/--severity/etc. CLI args

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to temp file with finding JSON")
    parser.add_argument("--findings-file", required=True, help="Path to docs-verify-findings.json")
    args = parser.parse_args()

    # Read input from temp file
    input_data = load_json(args.input)
    if input_data is None:
        save_rejected(args.input, "Input file not found or empty")
        sys.exit(1)

    # Validate
    is_valid, error = validate_finding(input_data)
    if not is_valid:
        save_rejected(args.input, error)
        sys.exit(1)

    # Load existing, append, save atomically
    findings = load_json(args.findings_file, default=[])
    findings.append(input_data)
    save_json(args.findings_file, findings)
```

### Pattern 3: Filter/Query Script (list-verify-findings.py)
**What:** Script reads consolidated findings file, applies filters, writes filtered results to `--output` temp file for agent to read.
**When to use:** Generate command and writer agents need filtered views of verify findings.
**Example:**
```python
# Three modes from CONTEXT.md:
# --summary: counts by severity and document
# --document OPERATIONS --audience devops: findings for a specific writer
# --severity high: filtered by minimum severity

def filter_findings(findings, document=None, audience=None, severity=None):
    """Filter findings by optional criteria."""
    result = findings
    if document:
        result = [f for f in result if f["document"] == document]
    if audience:
        result = [f for f in result if f["audience"] == audience]
    if severity:
        min_rank = SEVERITY_ORDER.index(severity)
        result = [f for f in result if SEVERITY_ORDER.index(f["severity"]) >= min_rank]
    return result

def build_summary(findings):
    """Build summary dict with counts by severity and document."""
    summary = {"total": len(findings), "by_severity": {}, "by_document": {}}
    for f in findings:
        sev = f["severity"]
        doc = f["document"]
        summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
        summary["by_document"][doc] = summary["by_document"].get(doc, 0) + 1
    return summary
```

### Pattern 4: Rejected Input Handling
**What:** When validation fails, save the invalid input to a `.rejected` file for debugging. Script exits non-zero but pipeline continues.
**When to use:** All new scripts that accept external input.
**Example:**
```python
def save_rejected(input_path, reason):
    """Save rejected input for debugging."""
    rejected_path = input_path + ".rejected"
    try:
        with open(input_path, "r") as f:
            content = f.read()
    except OSError:
        content = "<file not readable>"
    rejected = {"reason": reason, "original_input": content}
    with open(rejected_path, "w", encoding="utf-8") as f:
        json.dump(rejected, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Rejected input saved to {rejected_path}: {reason}", file=sys.stderr)
```

### Pattern 5: Scan Output Validation (write-scan-output.py)
**What:** Validates scan agent output structure before writing to scan-logs. Checks `source_material_index` keys follow `DOCUMENT/section-slug` format, required fields exist.
**When to use:** Part B -- scan agents call this instead of writing JSON directly.
**Example:**
```python
KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+/[a-z0-9]+(?:-[a-z0-9]+)*$")

def validate_scan_output(data, audience):
    """Validate scan output structure. Returns (is_valid, errors)."""
    errors = []
    if "source_material_index" not in data:
        errors.append("Missing required field: source_material_index")
    else:
        for key in data["source_material_index"]:
            if not KEY_PATTERN.match(key):
                errors.append(f"Invalid key format: '{key}' (expected DOCUMENT/section-slug)")
    if "gap_analysis" not in data:
        errors.append("Missing required field: gap_analysis")
    return len(errors) == 0, errors
```

### Anti-Patterns to Avoid
- **Passing structured data through CLI args:** Shell metacharacter escaping breaks on content with quotes, backticks, dollar signs. Use `--input` file instead.
- **LLM writing JSON directly via Write tool:** LLMs can produce subtly malformed JSON (trailing commas, wrong types). Python script is the serialization boundary.
- **Agent reading consolidated findings directly:** Generate/writer agents should use filter scripts, not read raw `docs-verify-findings.json`.
- **Nesting or deduplication in findings JSON:** Flat array, one entry per issue. Aggregation happens in presentation (markdown report), not data.
- **Task prompt overrides for agent behavior:** Phase 6 bakes behavior directly into agent definitions. No more override blocks in command files.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON atomic writes | Direct `open()/write()/close()` | `lib/json_io.save_json()` | Handles temp file + `os.replace()` + `makedirs` automatically |
| JSON loading with defaults | Try/except around `json.load()` | `lib/json_io.load_json(path, default=[])` | Consistent null handling across all scripts |
| Argument parsing | Manual `sys.argv` parsing | `argparse.ArgumentParser()` | Validation, help text, error messages for free |
| Finding validation | Inline field checks scattered through code | Centralized `validate_finding()` function | Single source of truth for required fields |

**Key insight:** Every pattern needed already exists in the codebase. `add-finding.py` demonstrates per-finding append. `add-note.py` demonstrates `lib/json_io` usage. `merge-scan.py` demonstrates reading scan-logs. The new scripts are compositions of existing patterns with file-based I/O replacing CLI-args I/O.

## Common Pitfalls

### Pitfall 1: Generate Exit Condition Regression
**What goes wrong:** The current exit condition in `create-docs-generate.md` (Step 2a, line 63) is "if both the staleness report is empty AND there are no pending notes, exit with 'Nothing to update.'" Adding verify findings as a 3rd tier requires updating this condition to also check for findings.
**Why it happens:** Easy to add the 3rd tier to the approval flow but forget to update the early-exit guard.
**How to avoid:** The exit condition must become: "if staleness empty AND no pending notes AND no verify findings, exit." Findings alone must prevent early exit.
**Warning signs:** Running generate after verify found issues produces "Nothing to update."

### Pitfall 2: Install.sh Script Inclusion
**What goes wrong:** New scripts work locally but fail in installed projects because they were not added to install.sh's copy loop.
**Why it happens:** install.sh copies `scripts/*.py` via wildcard (line 193-196), but the wildcard only works if the scripts are in the flat scripts/ directory (not subdirectories). The current wildcard pattern `"${SCRIPT_DIR}"/scripts/*.py` WILL pick up new scripts automatically.
**How to avoid:** Verify the wildcard glob includes new files. The existing `for py_file in "${SCRIPT_DIR}"/scripts/*.py` loop (line 193) handles this automatically. No install.sh code change needed for scripts -- only need to verify the sed placeholder resolution handles `{SCRIPTS_DIR}` in any new agent/command files that reference the scripts.
**Warning signs:** `python3: can't open file` errors in installed projects.

### Pitfall 3: Findings File Cleared at Wrong Time
**What goes wrong:** If `docs-verify-findings.json` is cleared in the wrong place (e.g., by generate instead of verify), findings are lost before they can be consumed.
**Why it happens:** CONTEXT.md specifies verify clears findings before each run, but generate reads them. If someone adds a clear step to generate "for safety," findings disappear.
**How to avoid:** Only `create-docs-verify.md` clears `docs-verify-findings.json` (at the start of each run). Generate reads and consumes but never clears.
**Warning signs:** Generate shows "no findings" immediately after verify reported issues.

### Pitfall 4: Severity Ordering in list-verify-findings.py
**What goes wrong:** Filtering by `--severity high` should return high AND critical, not just high. If the severity filter uses exact match instead of "at or above," the generate command won't see critical findings when filtering by severity.
**Why it happens:** Simple string equality instead of rank-based comparison.
**How to avoid:** Use the same severity ordering pattern as `merge-scan.py` (line 31-39): define `SEVERITY_ORDER`, use index comparison for "at or above" semantics.
**Warning signs:** `--severity medium` only returns medium, not medium + high + critical.

### Pitfall 5: Scanner Output Backwards Compatibility
**What goes wrong:** Part B's `write-scan-output.py` validates and writes scan output, but `merge-scan.py` reads from the same `scan-logs/` directory. If the new script writes a different structure than what merge-scan expects, the merge breaks.
**Why it happens:** Schema drift between the write path (new script) and the read path (existing merge-scan.py).
**How to avoid:** `write-scan-output.py` MUST produce the same top-level structure that `merge-scan.py` expects: `source_material_index`, `gap_analysis` (and optionally `staleness_report`, `note_classifications`). Validate against the same schema that merge-scan reads.
**Warning signs:** `merge-scan.py` warnings about skipping files after scan agents use the new script.

### Pitfall 6: Verifier Agent Rewrite Losing Check Details
**What goes wrong:** The verifier.md rewrite needs to preserve the detailed check logic (6 checks with specific severity mappings, cross-reference patterns) while changing the output workflow from report-only to findings-first.
**Why it happens:** Rewriting from scratch risks dropping nuanced severity rules (e.g., "broken file path = critical, missing symbol = high, ambiguous reference = medium").
**How to avoid:** Extract the check-specific logic from the current `verifier.md` verbatim before rewriting. The rewrite changes the output workflow (Step 1: per-finding via script, Step 2: report), not the check logic itself.
**Warning signs:** Verify findings have wrong severity levels or missing checks.

### Pitfall 7: Merged Drill-in Complexity in Generate
**What goes wrong:** The merged drill-in ("by document" shows both staleness sections AND verify findings) requires interleaving data from two different sources. Easy to show them in separate groups instead of merged.
**Why it happens:** Staleness data comes from `docs-scan.json`, findings come from `list-verify-findings.py`. Different structures need to be presented together per document.
**How to avoid:** When building the drill-in view, group by document name first, then list staleness sections and findings together under each document. Example: "OPERATIONS.md -- 2 stale sections, 3 verify findings".
**Warning signs:** "By document" approval shows staleness and findings as separate groups rather than merged per document.

## Code Examples

### Verify Finding JSON Shape (from CONTEXT.md)
```json
{
  "document": "OPERATIONS",
  "section": "deployment-pipeline",
  "audience": "devops",
  "severity": "high",
  "check": "reference-integrity",
  "description": "File path src/deploy/old-pipeline.sh referenced in section does not exist",
  "suggestion": "Update reference to src/deploy/pipeline.sh (renamed in commit abc1234)"
}
```

### add-verify-finding.py Interface
```bash
# Agent writes finding data to temp file first (via Write tool):
# /tmp/finding-001.json contains the JSON above

# Then calls:
python3 {SCRIPTS_DIR}/add-verify-finding.py \
  --input /tmp/finding-001.json \
  --findings-file .mg/docs/docs-verify-findings.json
```

### list-verify-findings.py Interface
```bash
# Summary mode (for generate's approval UI):
python3 {SCRIPTS_DIR}/list-verify-findings.py \
  --findings-file .mg/docs/docs-verify-findings.json \
  --summary \
  --output /tmp/findings-summary.json

# Filter by document and audience (for writer agents):
python3 {SCRIPTS_DIR}/list-verify-findings.py \
  --findings-file .mg/docs/docs-verify-findings.json \
  --document OPERATIONS \
  --audience devops \
  --output /tmp/findings-ops.json

# Filter by severity:
python3 {SCRIPTS_DIR}/list-verify-findings.py \
  --findings-file .mg/docs/docs-verify-findings.json \
  --severity high \
  --output /tmp/findings-high.json
```

### write-scan-output.py Interface
```bash
# Agent writes complete scan output to temp file first (via Write tool):
# /tmp/scan-developers.json contains the full scan output

# Then calls:
python3 {SCRIPTS_DIR}/write-scan-output.py \
  --input /tmp/scan-developers.json \
  --output .mg/docs/scan-logs/scan-developers.json \
  --audience developers
```

### Existing Pattern Reference: add-finding.py (codebase-health)
```python
# Source: codebase-health/scripts/add-finding.py lines 51-71, 156-162
# This is the precedent for the per-finding append pattern.
# Key operations: load_array -> append -> save_array (atomic)
# Phase 6 difference: input from --input file, not CLI args
```

### Existing Pattern Reference: lib/json_io.py
```python
# Source: create-docs/scripts/lib/json_io.py
# load_json(path, default=None) -- returns default if file missing
# save_json(path, data) -- atomic write via temp file + os.replace
# ALL new scripts MUST use these functions
```

### Test Pattern: subprocess invocation
```python
# Source: create-docs/scripts/tests/test_add_note.py lines 13-17, 23-48
# Tests invoke scripts via subprocess.run() for CLI interface testing
# Key pattern: tempdir + write seed data + run script + verify output
SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "add-verify-finding.py",
)

def test_append_finding(self):
    with tempfile.TemporaryDirectory() as tmp:
        findings_file = os.path.join(tmp, "findings.json")
        input_file = os.path.join(tmp, "input.json")
        # Write input temp file
        with open(input_file, "w") as f:
            json.dump({"document": "OPERATIONS", ...}, f)
        # Run script
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--input", input_file,
             "--findings-file", findings_file],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CLI args for data (`--evidence "text..."`) | File-based I/O (`--input /tmp/data.json`) | Phase 6 | Eliminates shell metacharacter escaping bugs |
| Task prompt overrides for agent behavior | Behavior baked into agent definition | Phase 6 | Simpler command files, single source of truth |
| Verify produces report only | Verify produces findings JSON + report | Phase 6 | Enables feedback loop to generate |
| 2-tier approval (staleness + notes) | 3-tier approval (staleness + findings + notes) | Phase 6 | Complete update context for user |
| Scan agents write JSON directly | Scan agents -> validation script -> JSON | Phase 6 | Prevents malformed scan output |

**Deprecated/outdated:**
- Task prompt OVERRIDE blocks in `create-docs-verify.md` -- replaced by baking behavior into `verifier.md`
- The `create-docs-verify.md` principle "Do not modify the verifier agent file" -- Phase 6 IS the redesign, so the old constraint no longer applies
- Direct LLM JSON writes for scan output -- replaced by `write-scan-output.py`

## Open Questions

1. **Backwards compatibility of write-scan-output.py with existing scan-logs**
   - What we know: `merge-scan.py` reads all `*.json` in scan-dir via glob. It expects `source_material_index` and `gap_analysis` fields.
   - What's unclear: Should `write-scan-output.py` accept any extra fields beyond the validated ones (pass-through) or strip them?
   - Recommendation: Pass through extra fields -- validate required fields strictly, preserve everything else. This matches the defensive reading pattern in `merge-scan.py` (it skips unknown fields gracefully).

2. **Where does `docs-verify-findings.json` live in the file location convention?**
   - What we know: CONTEXT.md says `.mg/docs/`. Schema.md's file location convention (line 330-341) lists workspace files.
   - What's unclear: Already clear -- `.mg/docs/docs-verify-findings.json` alongside `docs-scan.json` and `docs-verify-report.md`.
   - Recommendation: Add to schema.md's file location convention diagram.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `python3 -m pytest`) |
| Config file | `pyproject.toml` (minimal -- name, version, dev deps) |
| Quick run command | `python3 -m pytest create-docs/scripts/tests/ -x` |
| Full suite command | `python3 -m pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| N/A (add-verify-finding) | Append finding to flat array, validate 7 required fields, reject invalid | unit | `python3 -m pytest create-docs/scripts/tests/test_add_verify_finding.py -x` | Wave 0 |
| N/A (add-verify-finding) | Save rejected input to .rejected file | unit | `python3 -m pytest create-docs/scripts/tests/test_add_verify_finding.py -x` | Wave 0 |
| N/A (list-verify-findings) | Filter by document, audience, severity | unit | `python3 -m pytest create-docs/scripts/tests/test_list_verify_findings.py -x` | Wave 0 |
| N/A (list-verify-findings) | Summary mode with counts by severity and document | unit | `python3 -m pytest create-docs/scripts/tests/test_list_verify_findings.py -x` | Wave 0 |
| N/A (write-scan-output) | Validate key format DOCUMENT/section-slug | unit | `python3 -m pytest create-docs/scripts/tests/test_write_scan_output.py -x` | Wave 0 |
| N/A (write-scan-output) | Validate required fields, reject invalid | unit | `python3 -m pytest create-docs/scripts/tests/test_write_scan_output.py -x` | Wave 0 |
| N/A (install) | install.sh includes new scripts in copy | smoke | manual -- run `./create-docs/install.sh --project /tmp/test-install` | manual-only |

### Sampling Rate
- **Per task commit:** `python3 -m pytest create-docs/scripts/tests/ -x`
- **Per wave merge:** `python3 -m pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `create-docs/scripts/tests/test_add_verify_finding.py` -- tests for add-verify-finding.py
- [ ] `create-docs/scripts/tests/test_list_verify_findings.py` -- tests for list-verify-findings.py
- [ ] `create-docs/scripts/tests/test_write_scan_output.py` -- tests for write-scan-output.py

## Sources

### Primary (HIGH confidence)
- **Codebase analysis** -- Direct examination of all files that Phase 6 modifies:
  - `codebase-health/scripts/add-finding.py` -- precedent for per-finding append pattern
  - `create-docs/scripts/add-note.py` -- precedent for `lib/json_io` usage and CLI pattern
  - `create-docs/scripts/merge-scan.py` -- reads scan-logs, defines expected input format for Part B compatibility
  - `create-docs/scripts/lib/json_io.py` -- atomic I/O utilities all scripts must use
  - `create-docs/agents/verifier.md` -- current agent definition (to be rewritten)
  - `create-docs/agents/scan-audience.md` -- current Output section (to be updated)
  - `create-docs/commands/create-docs-generate.md` -- 465-line command with 2-tier approval
  - `create-docs/commands/create-docs-verify.md` -- current verify command with Task prompt overrides
  - `create-docs/commands/create-docs.md` -- current router with 4 routes
  - `create-docs/install.sh` -- install process with wildcard script copy
  - `create-docs/references/schema.md` -- shared data contract
  - Existing test suites for pattern reference

### Secondary (MEDIUM confidence)
- **CONTEXT.md** -- User decisions from interactive discussion (comprehensive, locked decisions)

### Tertiary (LOW confidence)
- None -- all findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero external dependencies, all stdlib, verified against existing scripts
- Architecture: HIGH -- all patterns already exist in codebase, Phase 6 composes them
- Pitfalls: HIGH -- identified from direct codebase analysis and CONTEXT.md specifics

**Research date:** 2026-03-17
**Valid until:** indefinite (internal codebase patterns, not external library versions)
