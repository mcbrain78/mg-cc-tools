# Phase 6: Fix Verify Feedback Loop and Scan Output - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning
**Source:** Merged — context import (CONCEPT.md) + interactive discussion (2026-03-17)

<domain>
## Phase Boundary

Fix the broken verify-generate feedback loop so verify findings flow back into generate as a 3rd approval tier, and replace direct LLM JSON writes in scan agents with a validation script. Both changes follow the principle: LLMs do analysis, Python scripts do serialization. Part A (verify feedback loop) and Part B (scan output validation) are independent work streams — no dependency between them.

</domain>

<decisions>
## Implementation Decisions

### Part A vs Part B independence
- Parts A and B are independent work streams with no dependency between them
- Part A (verify feedback loop) is the priority — fixes the user-facing problem
- Part B (scan output validation) is hardening that prevents future drift
- They share `install.sh` changes but touch different agents and commands
- Can be parallel plans or sequential — planner's choice

### Verify findings JSON shape
- Flat array in `docs-verify-findings.json` stored in `.mg/docs/`
- One entry per document/section/issue — no nesting, no dedup logic
- Required fields per finding: `document`, `section`, `audience`, `severity`, `check`, `description`, `suggestion`
- If the same root cause appears in 4 documents, that's 4 findings — each tells generate exactly which section needs regeneration and why
- Aggregation into systemic patterns happens at the presentation layer (the markdown report), not in the JSON

### Verifier agent workflow — two steps
- Step 1 (per-finding, during checks): Agent runs 6 checks. Each issue discovered → agent writes a temp JSON file with finding data (structured fields + prose description/suggestion) → calls `add-verify-finding.py --input /tmp/finding.json`. Script validates and appends to consolidated findings file. Agent captures prose while analysis context is fresh.
- Step 2 (report generation, after all checks): Agent reads accumulated findings via `list-verify-findings.py --output /tmp/all-findings.json` + Read tool, identifies patterns across findings (e.g., same broken reference in 4 documents), writes `docs-verify-report.md` with editorial synthesis — grouping systemic issues, adding summary table, cross-referencing. This is presentation-layer aggregation, not data-layer.

### Generate consumption of verify findings
- Generate and writer agents never read `docs-verify-findings.json` directly
- They use filter scripts that write output to temp files (read via the Read tool):
  - `list-verify-findings.py --summary --output /tmp/findings-summary.json` → counts by severity and document (for generate's approval UI)
  - `list-verify-findings.py --document OPERATIONS --audience devops --output /tmp/findings-ops.json` → findings for a specific writer agent
  - `list-verify-findings.py --severity high --output /tmp/findings-high.json` → filtered view
- All data flows through files, never through shell boundaries

### Generate approval flow — 3rd tier for verify findings
- Generate command in update mode reads 3 inputs: staleness report, notes inbox, verify findings
- Verify findings read via `list-verify-findings.py --summary --output` + Read tool
- **Tier ordering:** Staleness (code changed) → Verify findings (quality issues) → Notes (user knowledge). Logical severity ordering.
- **Exit condition:** Findings alone prevent early exit. Current logic ("nothing to update" if no staleness + no notes) must include findings check. If verify found issues, there's work to do even if code hasn't changed.
- **Uniform approval:** The same 4 options (approve all / by document / by severity / cancel) apply across all 3 tiers in a single decision point. "Approve all" means all staleness + all findings + all notes.
- **Merged drill-in:** When user picks "by document", show staleness sections AND verify findings for that document together (e.g., "OPERATIONS.md — 2 stale sections, 3 verify findings"). One approval per document covers both.
- Writer agents receive approved verify findings as context via `list-verify-findings.py --document X --audience Y --output` + Read tool with instruction: "the previous version had this specific error, fix it"

### Finding lifecycle
- Verify command clears `docs-verify-findings.json` before each new verification run (same as how generate clears `terms-*.json` before each generation run)
- After generate processes findings and writers fix issues, the next verify run produces a fresh findings file reflecting current state
- Findings the user skips in generate's approval flow reappear on the next verify run — this is correct behavior, not a bug

### No fixability classification
- All findings are presented in generate's approval flow — the user decides what to approve
- Documentation is never truly blocked — there's always something to write, even if source material is incomplete
- No `fixability` field needed

### File-based I/O pattern (shared across Parts A and B)
- All data flows through files, never through shell boundaries
- Input: scripts accept `--input` pointing to a temp file the agent writes via the Write tool
- Output: scripts accept `--output` to write results to a file the agent reads via the Read tool
- This avoids shell metacharacter escaping on input and stdout formatting quirks on output

### Strict validation, graceful degradation
- Scripts validate input strictly — invalid JSON or missing required fields cause reject
- Rejected input saved to a `.rejected` file for debugging
- Pipeline continues without the failed item — every failure degrades to "that input is absent"
- All downstream consumers handle absent inputs gracefully

### Script handles all formatting
- Python script is the serialization boundary
- Agent provides values, script handles JSON structure, atomic writes (temp file + `os.replace`), and schema validation

### Scan output validation script (`write-scan-output.py`)
- Replaces direct JSON writes from scan agents
- Agent writes data to temp file → calls `write-scan-output.py --input /tmp/scan-developers.json --output scan-logs/scan-developers.json --audience developers`
- Script validates required fields (`source_material_index`, `gap_analysis`, correct key format `DOCUMENT/section-slug`)
- Writes validated JSON atomically
- Scan agents produce complete output per audience (not incremental), so the pattern is one validation call per audience, not per-finding

### Verifier agent modification strategy
- **Rewrite `verifier.md` directly** — the Phase 5 constraint ("never modify agent definitions") protected against small tweaks breaking shared infra, but Phase 6 IS a redesign of the verifier workflow. The old workflow is obsolete.
- **Bake LSP symbol verification into agent definition** — no more Task prompt overrides for Check 1. The agent definition itself specifies LSP go-to-definition for symbol checks.
- **Bake glossary reconciliation into agent definition** — fold the Phase 5 "ADDITIONAL" override for glossary-reconciliation.log into Check 2. Eliminates all Task prompt overrides.
- **Script paths passed as input parameters** — verifier agent receives `scripts_dir` as a parameter in the Task prompt (same pattern as `project_root`, `docs_dir`). Consistent with how all agents receive paths.
- **Result:** `create-docs-verify.md` simplifies to just parameter passing — no override blocks. `verifier.md` is the single source of truth for the verification workflow.

### Router awareness of verify findings
- **Add findings-aware state** to `create-docs.md` router. If `docs-verify-findings.json` exists and is non-empty, router says "Verify found issues — run generate to address them."
- **Check position:** After the existing verify report check (current final state). Sub-check: if findings JSON also exists and non-empty, route to "re-run generate." If findings empty or absent, route to "pipeline complete."
- **Simple file check:** Router reads `docs-verify-findings.json` directly and checks if array is non-empty. No script dependency (`list-verify-findings.py` not needed here).
- **Update router guidance:** When findings exist, say "Run `/mg:create-docs-generate` to address verify findings" — not the old broken advice about re-scanning.

### Implementation scope — Part A files
- `create-docs/scripts/add-verify-finding.py` — **New.** Accept finding via `--input` temp file, validate, append to `docs-verify-findings.json`. Medium complexity.
- `create-docs/scripts/list-verify-findings.py` — **New.** Filter/query findings: `--summary`, `--document`, `--audience`, `--severity`. Output to `--output` file. Medium complexity.
- `create-docs/scripts/tests/test_add_verify_finding.py` — **New.** Tests for add script. Medium complexity.
- `create-docs/scripts/tests/test_list_verify_findings.py` — **New.** Tests for list script. Medium complexity.
- `create-docs/agents/verifier.md` — **Full rewrite.** Two-step workflow with script calls, LSP baked in, glossary reconciliation baked in. High complexity.
- `create-docs/commands/create-docs-generate.md` — **Add 3rd approval tier.** Tier ordering: staleness → findings → notes. Uniform 4-option approval. Merged drill-in per document. Exit condition includes findings. High complexity.
- `create-docs/commands/create-docs-verify.md` — **Simplify.** Remove all Task prompt overrides (now baked into agent). Clear prior findings before run. Pass script paths to agent. Update Step 4 messaging. Medium complexity.
- `create-docs/commands/create-docs.md` — **Add findings-aware state.** Sub-check after verify report: if findings non-empty, route to re-run generate. Update guidance text. Low complexity.
- `create-docs/references/schema.md` — **Document format.** Add verify findings JSON schema. Low complexity.
- `create-docs/install.sh` — **Add scripts.** Include `add-verify-finding.py` and `list-verify-findings.py` in install list. Low complexity.

### Implementation scope — Part B files
- `create-docs/scripts/write-scan-output.py` — **New.** Accept scan output via `--input` temp file, validate schema, write atomically. Medium complexity.
- `create-docs/scripts/tests/test_write_scan_output.py` — **New.** Tests for the script. Medium complexity.
- `create-docs/agents/scan-audience.md` — **Update Output section.** Agent writes data to temp file, calls `write-scan-output.py --input` instead of writing JSON directly. Medium complexity.
- `create-docs/commands/create-docs-scan.md` — **Update agent spawn.** Pass script path to scan agents. Low complexity.
- `create-docs/install.sh` — **Add script.** Include `write-scan-output.py` in install list. Low complexity.

### Claude's Discretion
- Internal structure of `add-verify-finding.py` and `list-verify-findings.py` (argparse patterns, error handling style)
- How to split Part A into plans (scripts+tests first vs agent changes first vs all together)
- Whether to sequence Part A and Part B or parallelize them
- Test fixtures and test organization
- Exact approval flow UX wording (Level 1 overview formatting, drill-in presentation)
- How `write-scan-output.py` handles backwards compatibility with existing LLM-written scan-logs

</decisions>

<specifics>
## Specific Ideas

- The verify findings JSON shape is explicitly defined in the CONCEPT.md with a concrete example showing all 7 required fields
- The file-based I/O pattern addresses a latent bug in `codebase-health/scripts/add-finding.py` where shell metacharacters in CLI args would be interpreted by bash — a separate todo exists for that fix
- The codebase-health pipeline's `add-finding.py` is the precedent for the per-finding script pattern — verify findings follow the same principle
- Generate command is 465 lines with a 2-tier approval UX — the 3rd tier needs careful integration
- The `check-references.py` performance fix (index-based lookup + `--skip-symbol-check`) was already applied during Phase 5 validation

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `codebase-health/scripts/add-finding.py`: Precedent for per-finding script pattern — verify findings follow same principle (LLM calls script per issue, script validates + appends)
- `create-docs/scripts/merge-scan.py`: Already handles reading existing scan-logs — Part B's `write-scan-output.py` replaces the write path but merge still reads

### Established Patterns
- File-based I/O pattern: New scripts use `--input`/`--output` temp files instead of CLI args for data, avoiding shell metacharacter issues
- Atomic writes via `os.replace`: Established in existing scripts, must be followed by new scripts
- Schema validation in Python scripts: Scripts validate required fields and reject invalid input

### Integration Points
- `create-docs/commands/create-docs-generate.md` Step 2: Add 3rd approval tier (staleness → findings → notes), update exit condition, merged drill-in
- `create-docs/commands/create-docs-verify.md`: Simplify — remove all Task prompt overrides, clear findings before run, pass script paths
- `create-docs/commands/create-docs.md`: Add findings-aware state after verify report check, update guidance text
- `create-docs/agents/verifier.md`: Full rewrite — two-step workflow, LSP baked in, glossary reconciliation baked in
- `create-docs/agents/scan-audience.md`: Output section update — temp file + script instead of direct Write
- `create-docs/install.sh`: Must include 3 new scripts in install list

</code_context>

<deferred>
## Deferred Ideas

- Shell metacharacter fix in `codebase-health/scripts/add-finding.py` — filed as separate todo (`.planning/todos/pending/2026-03-17-fix-shell-metacharacter-escaping-in-add-finding-cli-args.md`)

</deferred>

---

*Phase: 06-fix-verify-feedback-loop-and-scan-output*
*Context gathered: 2026-03-17 via context import + interactive discussion*
