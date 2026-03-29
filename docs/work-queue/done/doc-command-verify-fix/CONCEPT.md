# Documentation Pipeline: Structured Output & Verify-Generate Feedback Loop

## Problems

### 1. Verify-Generate Feedback Loop is Broken

The documentation pipeline is unidirectional: scan → generate → verify → dead end. The verify step finds legitimate issues (broken references, factual errors, missing procedures, glossary conflicts) but nothing consumes that output. The verify command tells users to "re-run `/mg:create-docs-generate` after a fresh scan," but:

1. Generate in update mode only reads two inputs: staleness report and notes inbox
2. A re-scan produces an empty staleness report because the **code** hasn't changed — only the **docs** are wrong
3. Result: generate says "nothing to update" despite 21 known issues

Discovered during Phase 5 road-runner validation.

### 2. LLM Agents Write JSON Directly (Brittle)

The scan pipeline has per-audience agents (`scan-audience.md`) that write JSON directly via the Write tool. This is the same antipattern the codebase-health pipeline solved with `add-finding.py` — LLMs do analysis, deterministic scripts do serialization.

LLM-written JSON is brittle in practice: on long processes the output drifts (missing fields, wrong types, extra commentary, formatting errors). The codebase-health pipeline got this right by separating concerns. The create-docs pipeline should follow the same principle.

**Affected agents:**
- `agents/scan-audience.md` — writes `scan-logs/scan-{audience}.json` directly (source material index + gap analysis)
- `agents/verifier.md` — writes `docs-verify-report.md` directly (no structured JSON at all)

## Solution

Two changes with a shared principle: **LLMs do analysis, Python scripts do serialization.**

### Part A: Verify Findings Script + Generate Integration

Add a per-finding script for the verifier agent and consume the structured output as a 3rd input in generate's update approval flow.

**Pipeline after fix:**

```
scan → generate → verify (outputs findings.json + report.md)
                    ↓
         generate (reads findings.json as 3rd input, passes to writers)
```

**Verify findings JSON shape** (`docs-verify-findings.json` in `.mg/docs/`):

```json
[
  {
    "document": "OPERATIONS",
    "section": "database-schema",
    "audience": "devops",
    "severity": "high",
    "check": "reference-integrity",
    "description": "Schema name etl_runs should be road_runner",
    "suggestion": "Update schema reference to match actual database name"
  }
]
```

Flat array, one entry per document/section/issue. No nesting, no dedup logic. If the same root cause appears in 4 documents, that's 4 findings — each tells generate exactly which section needs regeneration and why. Aggregation into systemic patterns happens at the presentation layer (the markdown report), not in the JSON.

**Verifier agent workflow — two steps:**

1. **Per-finding (during checks):** Agent runs 6 checks. Each time it discovers an issue, it writes a temp JSON file with the finding data (structured fields + prose description/suggestion) and calls `add-verify-finding.py --input /tmp/finding.json`. The script validates and appends to the consolidated findings file. The agent captures the prose while it still has analysis context fresh.

2. **Report generation (after all checks):** Agent reads the accumulated findings via `list-verify-findings.py --output /tmp/all-findings.json` + Read tool, identifies patterns across findings (e.g., same broken reference in 4 documents), and writes `docs-verify-report.md` with editorial synthesis — grouping systemic issues, adding the summary table, cross-referencing. This is presentation-layer aggregation, not data-layer.

**Generate consumption — script-mediated, never raw JSON:**

Generate and writer agents never read `docs-verify-findings.json` directly. They use filter scripts that write output to temp files (read via the Read tool), avoiding shell formatting quirks on stdout:
- `list-verify-findings.py --summary --output /tmp/findings-summary.json` → counts by severity and document (for generate's approval UI)
- `list-verify-findings.py --document OPERATIONS --audience devops --output /tmp/findings-ops.json` → findings for a specific writer agent
- `list-verify-findings.py --severity high --output /tmp/findings-high.json` → filtered view

All data flows through files, never through shell boundaries. Agents read script output via the Read tool.

**Finding lifecycle:** The verify command clears `docs-verify-findings.json` before each new verification run (same as how generate clears `terms-*.json` before each generation run). After generate processes findings and writers fix issues, the next verify run produces a fresh findings file reflecting the current state. Findings the user skips in generate's approval flow reappear on the next verify run — this is correct behavior, not a bug.

**No fixability classification.** All findings are presented in generate's approval flow. The user decides what to approve. Documentation is never truly blocked — there's always something to write, even if source material is incomplete.

**Flow:**

1. Verify agent runs 6 checks, calls `add-verify-finding.py` per issue → accumulates `docs-verify-findings.json`
2. Verify agent reads findings via `list-verify-findings.py --output /tmp/all-findings.json` + Read tool, writes `docs-verify-report.md` with editorial synthesis
3. Verify command presents summary, guidance says "run `/mg:create-docs-generate` to address these issues"
4. Generate command in update mode reads 3 inputs:
   - Staleness report (source files changed)
   - Notes inbox (user-captured notes)
   - **Verify findings** via `list-verify-findings.py --summary --output /tmp/findings-summary.json` + Read tool (quality issues from last verification)
5. Generate approval flow presents verify findings as a 3rd tier
6. Writer agents receive approved verify findings as context via `list-verify-findings.py --document X --audience Y --output /tmp/findings-writer.json` + Read tool — "the previous version had this specific error, fix it"

### Part B: Scan Output Validation Script

Replace direct JSON writes from scan agents with a script that validates and serializes the output.

**Current (brittle):** Scan agent → Write tool → `scan-{audience}.json`

**After fix:** Scan agent → writes data to temp file → calls script with `--input /tmp/scan.json` → script validates schema + writes `scan-{audience}.json`

The scan agents produce complete output per audience (source material index + gap analysis), not incremental findings. So the pattern is different from verify: the script validates and writes the complete output in one call rather than appending per-finding.

**Scan output validation script** (`write-scan-output.py`):

```bash
python3 {SCRIPTS_DIR}/write-scan-output.py \
  --input /tmp/scan-developers.json \
  --output scan-logs/scan-developers.json \
  --audience developers
```

The script validates required fields (`source_material_index`, `gap_analysis`, correct key format `DOCUMENT/section-slug`), and writes the validated JSON atomically.

### Script Design Principles

**File-based I/O pattern.** All data flows through files, never through shell boundaries. Input: scripts accept `--input` pointing to a temp file the agent writes via the Write tool. Output: scripts accept `--output` to write results to a file the agent reads via the Read tool. This avoids shell metacharacter escaping on input and stdout formatting quirks on output. The agent writes data, the script reads data, and vice versa — no serialization crosses the shell boundary.

This addresses a latent bug in the existing `codebase-health/scripts/add-finding.py` where free-text CLI arguments (`--evidence`, `--notes`) containing shell metacharacters would be interpreted by bash before reaching the script. A separate todo has been filed for that fix.

**Strict validation, graceful degradation.** Scripts validate input strictly — invalid JSON or missing required fields cause the script to reject the input, warn to stderr, and save the rejected input to a `.rejected` file for debugging. The pipeline continues without the failed item. Every failure degrades to "that input is absent," which all downstream consumers handle gracefully.

**Script handles all formatting.** The Python script is the serialization boundary. The agent provides values, the script handles JSON structure, atomic writes (temp file + `os.replace`), and schema validation.

## Alternatives Considered

### Generate Reads Markdown Report Directly

Generate (an LLM) reads `docs-verify-report.md` and extracts findings.

**Rejected because:** The markdown report is written by an LLM (the verifier agent). Format drift is the same problem on both ends — an LLM writing prose that another LLM has to parse reliably. No structured intermediate means no guarantee of consistent field extraction across runs.

### Verify → Notes Channel

Verify creates inbox notes for each issue, user runs scan → generate to process them.

**Rejected because:**
- Requires 3 steps (verify → add-notes → scan → generate) instead of 1 (verify → generate)
- Notes are designed for "document this" not "fix this error"
- Requires user to manually create or approve note creation per issue
- Loses structured context (severity, check type, specific suggestion)

### LLM Agents Write JSON Directly

Skip the script, let agents write JSON via the Write tool (as scan agents do today).

**Rejected because:** LLM JSON output drifts on long processes — missing fields, wrong types, extra commentary. The scan pipeline's direct-write pattern is tech debt, not a pattern to follow.

### Aggregated JSON with Nested Occurrences

Group findings by root cause with nested `occurrences` arrays, using an `issue_key` for dedup.

**Rejected because:** Aggregation is a presentation concern, not a data concern. Generate needs per-document/section granularity for routing to writer agents. The verifier agent handles aggregation editorially when writing the markdown report (step 2) — same as it does today, just reading structured JSON instead of raw check-references output.

### Fixability Classification

Add a `fixability` field (`regenerable`, `needs-content`, `blocked`) to each finding.

**Rejected because:** Documentation is never truly blocked — there's always something to write. A missing directory can be documented as "created on first run." A missing runbook can be documented as "procedure TBD." The user decides what to approve in generate's approval flow. Premature classification adds complexity without value.

## Implementation Scope

### Part A: Verify Findings + Generate Integration

| File | Change | Complexity |
|------|--------|-----------|
| `create-docs/scripts/add-verify-finding.py` | **New.** Accept finding via `--input` temp file, validate, append to `docs-verify-findings.json`. | Medium |
| `create-docs/scripts/list-verify-findings.py` | **New.** Filter/query findings for consumers: `--summary`, `--document`, `--audience`, `--severity`. Output to `--output` file (read by agents via Read tool). | Medium |
| `create-docs/scripts/tests/test_add_verify_finding.py` | **New.** Tests for add script. | Medium |
| `create-docs/scripts/tests/test_list_verify_findings.py` | **New.** Tests for list script. | Medium |
| `create-docs/agents/verifier.md` | **Rewrite workflow.** Step 1: call `add-verify-finding.py` per issue. Step 2: read via `list-verify-findings.py`, write markdown report with editorial synthesis. | High |
| `create-docs/commands/create-docs-generate.md` | **Add 3rd approval tier.** Step 2 reads findings via `list-verify-findings.py --summary --output` + Read tool, presents alongside staleness + notes, passes findings to writer agents via `list-verify-findings.py --document X --output` + Read tool. | High |
| `create-docs/commands/create-docs-verify.md` | **Update guidance.** Clear prior findings before run. Pass script paths to agent. Update Step 4 messaging. | Low |
| `create-docs/references/schema.md` | **Document format.** Add verify findings JSON schema. | Low |
| `create-docs/install.sh` | **Add scripts.** Include `add-verify-finding.py` and `list-verify-findings.py` in install list. | Low |

### Part B: Scan Output Validation

| File | Change | Complexity |
|------|--------|-----------|
| `create-docs/scripts/write-scan-output.py` | **New.** Accept scan output via `--input` temp file, validate schema, write atomically. | Medium |
| `create-docs/scripts/tests/test_write_scan_output.py` | **New.** Tests for the script. | Medium |
| `create-docs/agents/scan-audience.md` | **Update Output section.** Agent writes data to temp file, calls `write-scan-output.py --input` instead of writing JSON directly. | Medium |
| `create-docs/commands/create-docs-scan.md` | **Update agent spawn.** Pass script path to scan agents. | Low |
| `create-docs/install.sh` | **Add script.** Include `write-scan-output.py` in install list (if not already covered by Part A change). | Low |

### Parts A and B are independent work streams

No dependency between them. Part A (verify feedback loop) is the priority — it fixes the user-facing problem. Part B (scan output validation) is hardening that prevents future drift. They share `install.sh` changes but touch different agents and commands. Can be parallel plans or sequential — planner's choice.

### Key Risks

1. **Generate approval flow complexity.** The generate command is 465 lines with a 2-tier approval UX. Adding a 3rd tier needs careful integration — the approval flow logic (approve all / by document / by severity / cancel) must handle verify findings consistently with staleness and notes.

2. **Verifier agent workflow change.** The agent currently accumulates findings in context and writes prose. Switching to per-finding script calls plus a report generation step changes the workflow fundamentally. The agent instructions need to clearly separate the two steps.

3. **Scan agent backwards compatibility.** Existing scan-logs from prior runs have LLM-written JSON. The validation script should be tolerant of reading existing files during merge (merge-scan.py already handles this).

### Validation

Full pipeline on road-runner:
1. Fresh scan → verify scan agents produce validated JSON via script
2. Generate → verify → confirm findings JSON produced and `list-verify-findings.py` returns correct data
3. Generate again → confirm 3rd approval tier shows verify findings via `--summary`
4. Writer fixes issues → verify again → confirm issues resolved (fewer findings)

**Edge cases to verify:**
- Invalid scan JSON → rejected with warning, scan continues without that audience
- Zero verify findings → empty array, generate skips 3rd tier
- Missing `docs-verify-findings.json` → generate ignores 3rd tier
- Writer doesn't fix issue → next verify rediscovers it

## Performance Fix Already Applied

During Phase 5 validation, `check-references.py` timed out on road-runner because `_symbol_exists_in_project()` walked the project tree per-symbol (O(symbols x files)). Two fixes applied:

1. **Index-based lookup:** Replaced per-symbol `os.walk` with a cached index built on first call. Subsequent lookups are O(1).
2. **`--skip-symbol-check` flag:** The verify command now passes this flag since symbol verification is delegated to LSP via the verifier agent.

These fixes are already committed and installed to road-runner.

## Related: Shell Metacharacter Bug in codebase-health

The temp file input pattern also addresses a latent bug in `codebase-health/scripts/add-finding.py` where free-text CLI arguments (`--evidence`, `--notes`) containing backticks, quotes, or dollar signs would be interpreted by bash before reaching the script. Filed as a separate todo: `.planning/todos/pending/2026-03-17-fix-shell-metacharacter-escaping-in-add-finding-cli-args.md`.
