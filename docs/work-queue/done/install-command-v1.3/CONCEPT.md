# Install Command v1.3 — Thin Orchestrator Refactor

## Problem Statement

The install command prompt (`install.md`) is 475 lines of conditional logic that the LLM must follow correctly. In practice, it doesn't:

1. **Skipped steps** — Step 2b (adoption check) was skipped entirely because the LLM didn't check for existing commands on disk when `manifest_exists` was false.

2. **Wrong scenario routing** — Step 3 has three scenario templates (A/B/C) selected by reading summary counts. The LLM must pick the right one, render the right menu, and map option numbers back to the right action — option [2] means different things in each scenario.

3. **State reconstruction** — Step 8 summary requires the LLM to reconstruct what happened across all tools (which succeeded, which failed, what commands were installed). This degrades as tool count grows.

4. **Repeated echo instructions** — The two rendering subcommands each need an explicit "Bash output is collapsed, you MUST echo this verbatim" instruction. The LLM still truncates (dropped the legend on first attempt).

5. **Install pattern determination** — Step 6 requires the LLM to read `has_install_sh` and `post_install` fields per tool and choose pattern A/B/C. This is a lookup table, not a judgment call.

## Root Cause

The prompt treats the LLM as a general-purpose computer that can reliably execute conditional logic, maintain state, and render output. It can't. Phase 10 moved rendering to Python for exactly this reason, but the flow logic itself is still LLM-driven.

The LLM IS necessary here — Claude Code has no stdin, so the LLM is the only way to present output and collect user input. But the LLM should be a thin UI bridge, not a state machine.

## Principle

**Everything deterministic goes to Python. The LLM only does:**
1. Echo output to the user (fenced code blocks)
2. Collect user input (chat responses, AskUserQuestion)
3. Spawn post-install subagents (Agent tool)
4. Light interpretation (free text → tool names, only when resolve-tool-selection fails)

**All new code stays stdlib-only**, consistent with the existing library (no pip dependencies).

## Solution

### New subcommands in mg-install-lib.py

#### 1. Auto-adopt via `--auto-adopt` flag on scan-status

Add an `--auto-adopt` flag to the existing `scan-status` subcommand. When the flag is set and `manifest_exists` is false, scan-status checks for existing installations (command files + detect paths) and runs `adopt_tools()` before computing statuses. The output includes `"auto_adopted": ["tool1", "tool2"]` when adoption occurred.

Without the flag, scan-status remains a pure read operation — no side effects.

**Prompt calls:** `python3 "$MG_INSTALL_LIB" scan-status --source ./ --target "$TARGET_PATH" --output /tmp/mg-scan-status.json --auto-adopt`

The LLM never checks `manifest_exists` or decides whether to adopt. One command handles everything.

**Replaces:** Step 2b's conditional check (if manifest missing → check disk → run adopt → re-scan).

**Prompt reduction:** ~18 lines → 0 lines (Step 2b is deleted entirely).

#### 2. `render-action-menu`

**Input:** `--input <scan-status-json>`
**Output:** The correct scenario menu as plain text to stdout.

**Logic:** Uses a shared `_determine_scenario(scan_data)` helper (see Design Constraint below) to select the scenario:
- **Scenario A:** `installed_total == 0` — nothing installed
- **Scenario B:** `update > 0 or modified > 0 or corrupt > 0 or adopted > 0` — some need attention
- **Scenario C:** `installed_total > 0` and none of B's conditions — all current

**Behavior change from v1.2:** Scenario B now triggers on `corrupt` and `adopted` statuses in addition to `update`/`modified`. Previously these fell through to Scenario C ("All current"), which offered no repair option. This is intentional — corrupt and adopted tools need attention, not a "reinstall all" menu.

Computes dynamic counts for menu labels:
- "N tools needing attention" = `summary.update + summary.modified + summary.corrupt + summary.adopted`
- "N remaining standard" = count of tools where `status == "available" and standard == true and excluded == false`
- "N tools" for bulk install = count of tools where `standard == true and excluded == false`

**Output examples:**

Scenario A (nothing installed):
```
What would you like to do?

  [1] Install all standard tools (N tools) (recommended)
  [2] Select specific tools
  [3] Edit standard install list

Type a number, or tool names separated by commas:
```

Scenario B (some need attention):
```
What would you like to do?

  [1] Fix/update N tools needing attention (recommended)
  [2] Fix/update + install all missing standard
  [3] Install missing standard only (N tools)
  [4] Edit standard install list
  [5] Check capabilities only

Type a number, tool names, or 'all':
```

Scenario C (all current):
```
What would you like to do?

  [1] Install remaining N standard tools
  [2] Reinstall all
  [3] Edit standard install list
  [4] Check capabilities only

Type a number, tool names, or 'all':
```

**Replaces:** Step 3's three scenario templates and the LLM's scenario selection logic.

**Prompt reduction:** ~50 lines → 5 lines ("run render-action-menu, echo stdout, get user response").

#### 3. `resolve-action`

**Input:** `--input <scan-status-json> --selection "<user_response>"`
**Output:** `{"action": "install", "tools": ["tool1", "tool2"]}` or `{"action": "select_specific"}` or `{"action": "edit_standard"}` or `{"action": "check_capabilities"}` or `{"error": "..."}`

**Logic:** Uses the shared `_determine_scenario(scan_data)` helper to derive the active scenario. Maps the user's menu selection to the correct action with a pre-computed tool list:

**Scenario A option mapping:**
- [1] Install all standard → `{"action": "install", "tools": [all standard non-excluded]}`
- [2] Select specific → `{"action": "select_specific"}`
- [3] Edit standard list → `{"action": "edit_standard"}`

**Scenario B option mapping:**
- [1] Fix/update N tools → `{"action": "install", "tools": [tools with status in (update, modified, corrupt, adopted)]}`
- [2] Fix/update + install missing → `{"action": "install", "tools": [option 1 tools + available standard non-excluded]}`
- [3] Install missing only → `{"action": "install", "tools": [available standard non-excluded]}`
- [4] Edit standard list → `{"action": "edit_standard"}`
- [5] Check capabilities → `{"action": "check_capabilities"}`

**Scenario C option mapping:**
- [1] Install remaining standard → `{"action": "install", "tools": [available standard non-excluded]}`
- [2] Reinstall all → `{"action": "install", "tools": [all non-excluded]}`
- [3] Edit standard list → `{"action": "edit_standard"}`
- [4] Check capabilities → `{"action": "check_capabilities"}`

For tool names/numbers (not a menu option), delegates to `resolve_tool_selection()` internally and returns `{"action": "install", "tools": [...]}`.

**Replaces:** Step 3's option→action mapping across three scenarios, and the "build final tool list" logic.

**Prompt reduction:** ~20 lines → 3 lines ("run resolve-action, follow the returned action").

#### 4. `get-install-plan`

**Input:** `--input <scan-status-json> --tools <comma-separated-list>`

The scan-status JSON contains the `target` path — `get-install-plan` reads it from there to produce fully-resolved shell commands. No `--target` argument needed.

**Output:** JSON array of install instructions:
```json
[
  {"tool": "create-docs", "pattern": "copy_only", "expected_action": "installed", "install_cmd": "bash ./create-docs/install.sh --target \"/home/user/projects/road-runner/.claude\"", "post_install": null, "commands": ["create-docs.md", "create-docs-scan.md", "create-docs-generate.md", "create-docs-verify.md", "add-docs.md"]},
  {"tool": "permission-hooks", "pattern": "copy_configure", "expected_action": "updated (configured)", "install_cmd": "bash ./permission-hooks/install.sh --target \"/home/user/projects/road-runner/.claude\"", "post_install": "permission-hooks/post-install.md", "commands": []},
  {"tool": "gsd-patches", "pattern": "execute_only", "expected_action": "installed (configured)", "install_cmd": null, "post_install": "gsd-patches/post-install.md", "commands": ["apply-gsd-patches.md"]}
]
```

**Logic:** Reads `has_install_sh` and `post_install` fields per tool from scan-status, determines install pattern:
- `copy_only` = has_install_sh && !post_install
- `copy_configure` = has_install_sh && post_install
- `execute_only` = !has_install_sh && post_install

Pre-computes `expected_action` from the tool's current status and pattern:
- `status == "available"` → `"installed"`
- `status in ("update", "modified", "corrupt", "adopted")` → `"updated"`
- `status == "current"` → `"reinstalled"`

If the pattern is `copy_configure` or `execute_only`, the action gets a `" (configured)"` suffix (e.g., `"installed (configured)"`, `"updated (configured)"`) so the summary can show both the status transition and the post-install note.

Includes the `commands` list from scan-status per tool (read from the full `--output` file). This data flows through to `record-result` so the LLM never needs to provide command filenames.

**Replaces:** Step 6's per-tool pattern determination logic.

**Prompt reduction:** ~15 lines → iteration loop.

#### 5. `render-preflight`

**Input:** `--input <preflight-json>` (the `--output` file from the existing `preflight` subcommand)
**Output:** Formatted preflight results to stdout (human-readable only — no JSON mixed in).

**Prerequisite:** The existing `preflight` subcommand gains `--output` support (same pattern as `scan-status` and `validate`). The prompt calls:
```bash
python3 "$MG_INSTALL_LIB" preflight --source ./ --target "$TARGET_PATH" --tools "tool1,tool2" --output /tmp/mg-preflight.json
```
This writes full results to file and compact summary to stdout. The compact summary already includes `all_passed`. The prompt checks `all_passed` from the compact stdout JSON — if false, abort. If true, run `render-preflight` for display:
```bash
python3 "$MG_INSTALL_LIB" render-preflight --input /tmp/mg-preflight.json
```

**Logic:** Reads the preflight JSON, formats check results with PASS/FAIL markers, groups by required/optional, computes summary line. Pure rendering — no decision logic.

The `/tmp/mg-preflight.json` file is also consumed by `render-summary` for capability data.

**Replaces:** Step 4's result formatting.

**Prompt reduction:** ~30 lines → 5 lines (preflight call + abort check + render-preflight + echo).

#### 6. `record-result`

Simple append-only helper for building the install results file during Step 6.

**Input:** `--file <path> --tool <name> --success|--failed --plan <install-plan-json>`
**Output:** Appends one entry to the results JSON file.

**Logic:** Reads the install plan JSON (output of `get-install-plan`, saved to a temp file) to look up the tool's `commands` list and `expected_action`. The LLM only passes `--tool` and `--success`/`--failed` — no action or command filenames needed.

- On `--success`: writes `{"tool": "...", "action": "<expected_action>", "commands": [...]}`
- On `--failed`: writes `{"tool": "...", "action": "failed", "commands": []}`

Creates the file with `[]` if it doesn't exist. Each call reads the file, parses the JSON array, appends the new entry, and rewrites the file. No file locking needed — calls are sequential (one per tool in the install loop).

**File format after N calls:**
```json
[
  {"tool": "create-docs", "action": "installed", "commands": ["create-docs.md", "create-docs-scan.md"]},
  {"tool": "permission-hooks", "action": "updated (configured)", "commands": []},
  {"tool": "debug-triage", "action": "failed", "commands": []}
]
```

**Prompt calls:**
```bash
# Save install plan to file (once, before the install loop):
python3 "$MG_INSTALL_LIB" get-install-plan --input /tmp/mg-scan-status.json --tools "tool1,tool2" --output /tmp/mg-install-plan.json

# After each tool completes:
python3 "$MG_INSTALL_LIB" record-result --file /tmp/mg-install-results.json --tool "create-docs" --success --plan /tmp/mg-install-plan.json
```

`get-install-plan` uses `--output` (consistent with scan-status and validate) rather than stdout redirect. The LLM reads the returned compact JSON from stdout to iterate through the plan.

#### 7. `render-summary`

**Input:** `--results <install-results-json> --input <scan-status-json> --preflight <preflight-json>`
**Output:** Formatted summary table to stdout.

```bash
python3 "$MG_INSTALL_LIB" render-summary \
  --results /tmp/mg-install-results.json \
  --input /tmp/mg-scan-status.json \
  --preflight /tmp/mg-preflight.json
```

**Logic:** Reads the results file, formats the summary with action column, command filenames, counts. Merges capability data from preflight JSON (LSP status, missing optional tools) if the `--preflight` argument is provided.

**Replaces:** Step 8's LLM-reconstructed summary from memory.

**Prompt reduction:** ~35 lines → 3 lines ("run render-summary, echo output").

### Design constraint: shared scenario logic

`render-action-menu` and `resolve-action` MUST use a single shared `_determine_scenario(scan_data)` function for scenario derivation. Duplicating this logic is the exact class of bug this refactor eliminates — if one is updated and the other is not, option numbers would mean different things in the menu vs. the resolver.

### Prompt consolidation

Replace the two per-subcommand "IMPORTANT: echo verbatim" instructions with a single directive at the top of the prompt:

```markdown
**Rendering rule:** When you call a `render-*` subcommand (render-status-table,
render-action-menu, render-preflight, render-summary), its stdout is
user-facing content. You MUST copy the COMPLETE stdout and output it as a
fenced code block in your response. Bash tool output is collapsed in
Claude Code — the user cannot see it without expanding. Never truncate,
summarize, or omit lines.

Other subcommands (scan-status, resolve-action, get-install-plan, record-result)
output machine-readable JSON — do NOT echo these to the user.
```

### CLI argument convention

All new subcommands that read the scan-status file use `--input <path>`, matching the existing `render-status-table` and `render-tool-picker` subcommands. `render-summary` uses `--input` for scan-status, `--results` for the install results file, and `--preflight` for the optional preflight file.

### What stays in the prompt (LLM territory)

- **Step 1:** Target selection via AskUserQuestion (user interaction)
- **Step 3:** Edit Standard Install List sub-flow (interactive toggle loop — ~37 lines)
- **Step 5:** Capability check display (simple one-field conditional, rarely shown)
- **Step 6:** Agent spawning for post-install.md (genuinely needs LLM + Agent tool)
- **Step 6:** POST-INSTALL marker parsing (LLM reads Agent output)
- **Step 6:** Stop-on-error decision (LLM must halt the loop)
- **Free text fallback:** When resolve-action returns an error, LLM can try to interpret ("just the GSD tools")

### What gets deleted from the prompt

- Three scenario menu templates (A/B/C) → render-action-menu
- Option→action mapping tables → resolve-action
- Step 2b adoption check (entire section) → auto-adopt in scan-status
- Per-tool pattern determination (if/elif on fields) → get-install-plan
- Preflight result formatting → render-preflight
- Summary table construction from memory → render-summary + record-result
- Per-subcommand echo instructions (2x) → single display rule

## Expected result

The install.md prompt shrinks from ~475 lines to ~200-250 lines. The remaining lines are:
- Display rule (5 lines)
- Step 1: target selection (30 lines — unchanged)
- Step 3: Edit Standard Install List sub-flow (37 lines — unchanged)
- Step 6: Agent spawning + marker parsing + progress (~50 lines)
- Steps 2-8 orchestration glue (~80-100 lines)
- Key constraints (10 lines — simplified)

The orchestration loop for each step becomes:
```
run Python → echo output → [get user input → run Python] → next step
```

No conditional rendering. No scenario selection. No state reconstruction. No pattern determination. The LLM is a bridge between the user and the scripts.

## Files changed

- `install/scripts/mg-install-lib.py` — 6 new subcommands + scan-status `--auto-adopt` flag + shared `_determine_scenario()` + argparse wiring
- `install/scripts/tests/test_mg_install_lib.py` — tests for each subcommand
- `install/commands/install.md` — rewrite to thin orchestrator
- `.claude/commands/mg/install.md` — deployed copy (keep in sync)

## Not in scope

- Changes to install.sh scripts
- Changes to tool.toml format
- New features or capabilities — this is a reliability refactor with one deliberate behavior change (Scenario B expanded to include corrupt/adopted)
- Edit Standard Install List extraction to Python — stays in prompt for now (~37 lines, low usage)

## Success criteria

1. The install.md prompt is under 250 lines
2. The prompt contains zero conditional rendering (no "if scenario A... elif scenario B...")
3. All rendering and flow decisions are deterministic Python with pytest coverage
4. The LLM's only jobs are: echo output, collect input, spawn agents
5. The install flow produces identical user-visible output to v1.2, except: Scenario B now triggers on `corrupt`/`adopted` statuses (documented behavior change)
