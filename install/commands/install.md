---
name: mg:install
description: Install, update, and manage mg-cc-tools in target projects
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

# mg:install -- Unified Tool Installer & Manager

You are the **mg-cc-tools installer**. You install, update, and manage mg-cc-tools slash commands in target projects through an interactive 8-step flow.

**You always run from the mg-cc-tools directory.** The source is always `./` (the current working directory). The target is a separate project.

## Prerequisites

Before starting, verify you are in the mg-cc-tools directory:

```bash
test -f ./pyproject.toml && test -d ./install/scripts || echo "ERROR: Must run from mg-cc-tools directory"
```

Set the script path for all subsequent calls:

```bash
MG_INSTALL_LIB="./install/scripts/mg-install-lib.py"
```

---

## Step 1: Target Selection

Determine the target project.

**If `$ARGUMENTS` contains a path**, use it directly. Validate it exists:

```bash
test -d "$TARGET_PATH" || echo "ERROR: Directory does not exist: $TARGET_PATH"
```

**Otherwise**, check for recent targets and ask the user:

1. Read `~/.config/mg-cc-tools/targets.json` (if it exists). This file contains:
   ```json
   { "recent_targets": ["/path/to/project1", "/path/to/project2"] }
   ```

2. Build options from recent targets (most recent first, max 5 entries). Present via AskUserQuestion:
   ```
   AskUserQuestion (header: "Target Project", multiSelect: false)
     Q: "Which project do you want to manage tools for?"
     Options: (from recent targets + defaults)
       - "/home/user/projects/road-runner"
       - "/home/user/projects/other-project"
       - "Enter path manually"
   ```

   If no recent targets exist, ask:
   ```
   AskUserQuestion (header: "Target Project", multiSelect: false)
     Q: "Enter the path to the project you want to manage tools for:"
     Options:
       - "Enter path manually"
   ```

3. If the user selects "Enter path manually", ask for the path via a follow-up AskUserQuestion.

4. Validate the target path exists. If it does not have a `.claude/` directory, offer to create one:
   ```bash
   mkdir -p "$TARGET_PATH/.claude/commands/mg"
   ```

5. After successful target selection, update `~/.config/mg-cc-tools/targets.json`:
   - Add the selected path to the front of `recent_targets`
   - Remove duplicates
   - Keep max 5 entries
   - Create `~/.config/mg-cc-tools/` directory if needed

   Use the Write tool to update the file.

Store `TARGET_PATH` for all subsequent steps.

---

## Step 2: Status Scan

Run the status scan to discover tools and their installation state:

```bash
python3 "$MG_INSTALL_LIB" scan-status --source ./ --target "$TARGET_PATH"
```

This returns JSON with: `mg_cc_tools_version`, `target`, `manifest_exists`, `tools` array, and `summary` object.

**Format the output as a status table:**

```
mg-cc-tools (0.3.0) -- /home/user/projects/road-runner

  Tool                Description                                      Updated        Status
  -------------------------------------------------------------------------------------------
  create-docs         Documentation pipeline (scan, generate, verify)   2 hours ago    Update (0.2.0 -> 0.3.0)
  codebase-health     Scan, verify, and fix code health issues          3 days ago     Current (0.3.0)
  data-provider       Research and map external data field sources       5 days ago     Available
  ...
  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
  install             mg-cc-tools installer (internal)                   1 hour ago     - Excluded
  cc-regression-test  Claude Code regression test harness (internal)     1 week ago     - Excluded

  Installed: 6/11  |  Outdated: 1  |  Modified: 1  |  Current: 4  |  Available: 5
```

For the "Updated" column, get the last git commit time for each tool directory:
```bash
git log -1 --format="%cr" -- <tool-dir>/
```

Display it as relative time (e.g., "2 hours ago", "3 days ago").

**Status markers:**
- `Current (version)` -- installed, checksums match, version matches
- `Update (old -> new)` -- installed, but project version changed since install
- `Modified (N files)` -- installed, same version, but source file checksums differ
- `Corrupt` -- manifest says installed but command files missing on disk
- `Available` -- not installed
- `- Excluded` -- has `exclude = true` in tool.toml (shown below separator)

### Step 2b: Migration (if manifest missing but commands found)

If `manifest_exists` is `false` in the scan-status output, check if any tools show commands already present in the target. If so, suggest migration:

```
No manifest found, but existing mg-cc-tools commands detected in the target.
Running migration to adopt existing installations...
```

Run the adopt subcommand:
```bash
python3 "$MG_INSTALL_LIB" adopt --source ./ --target "$TARGET_PATH"
```

Show which tools were adopted, then re-run scan-status and display the updated table.

---

## Step 3: Action Selection

Present numbered options as a **plain text prompt** (NOT AskUserQuestion). The options adapt based on scan results.

Parse the `summary` from the scan-status output to determine the scenario.

**Scenario A: Nothing installed (summary.installed == 0)**
```
What would you like to do?

  [1] Install all tools (recommended)
  [2] Select specific tools

Type a number, or tool names separated by commas:
```

**Scenario B: Some outdated or modified (summary.outdated > 0 or summary.modified > 0)**
```
What would you like to do?

  [1] Update N outdated tools (recommended)
  [2] Update outdated + install all missing
  [3] Install missing only (N tools)
  [4] Check capabilities only

Type a number, tool names, or 'all':
```

**Scenario C: All current (summary.installed > 0 and summary.outdated == 0 and summary.modified == 0)**
```
What would you like to do?

  [1] Install remaining N tools
  [2] Reinstall all
  [3] Check capabilities only

Type a number, tool names, or 'all':
```

**Parse the user's response:**
- A number (1, 2, 3, 4) -- map to the corresponding action
- Tool names ("create-docs, codebase-health") -- install/update those specific tools
- "all" -- install/update all non-excluded tools
- Free text ("just the GSD tools", "pipeline tools") -- interpret and select matching tools

**Build the final tool list** based on the user's selection. Exclude tools with `excluded: true` from bulk operations (but allow them if the user names them explicitly).

If the user selects "Check capabilities only", skip to Step 5 (Capability Probe), then Step 8 (Summary).

---

## Step 4: Preflight Checks

Run preflight checks for the selected tools:

```bash
python3 "$MG_INSTALL_LIB" preflight --source ./ --target "$TARGET_PATH" --tools tool1 tool2 tool3
```

This returns JSON with: `checks` array (each with `name`, `status`, `version`, `required_by`, `fix` info) and `all_required_passed` boolean.

**Display results:**
```
Preflight checks:

  [PASS] python3    3.13.1    (required by: create-docs, codebase-health, data-provider, permission-hooks)
  [PASS] git        2.43.0    (used by: create-docs staleness detection)
  [PASS] gsd        found     (required by: debug-triage, mg-gsd-wrappers, update-backlog, new-milestone-gsd)
  [FAIL] ruff       missing   (optional: codebase-health scan degraded)
  [FAIL] vulture    missing   (optional: codebase-health dead code detection unavailable)

  Required: 3/3 passed
  Optional: 0/2 (degraded features noted)
```

**If `all_required_passed` is false (required check failed):**

Hard abort. Show the failing check's fix instructions:
```
PREFLIGHT FAILED

  python3 is required but not found.

  To fix:
    Ubuntu/Debian:  sudo apt install python3
    macOS:          brew install python3
    Other:          https://python.org/downloads

  After fixing, re-run /mg:install
```

Do NOT proceed to installation. Stop here.

**If only optional checks fail:**

Warn the user, note the degraded features, and continue:
```
Optional tools missing -- some features will be degraded. Continuing with install.
```

---

## Step 5: Capability Probe

Run the LSP capability probe from the **target project directory** (not from mg-cc-tools):

```bash
cd "$TARGET_PATH" && timeout 60 claude -p --output-format json "Try to use the LSP tool to look up any symbol definition in this project. Report ONLY a JSON object: {\"lsp_functional\": true/false, \"languages\": [...]}" 2>/dev/null; cd -
```

**Handle outcomes:**
- **Success with JSON response**: Parse `lsp_functional` and `languages` from the response
- **Timeout (60 seconds)**: Treat as LSP not available
- **Parse error or non-JSON response**: Treat as LSP not available
- **Command not found (claude not available)**: Treat as LSP not available

**Display result:**
```
Capabilities:
  LSP: functional (python, javascript)
```

Or:
```
Capabilities:
  LSP: not available
  Note: create-docs-verify symbol verification will use extraction only
```

**LSP unavailability is never blocking.** It is informational only. Continue to Step 6 regardless of the probe result.

---

## Step 6: Execute Installs

For each tool in the final tool list, run its `install.sh`:

```bash
bash ./<tool-name>/install.sh --target "$TARGET_PATH/.claude"
```

**IMPORTANT:** The `--target` argument points to the `.claude` directory inside the target project.

Display progress for each tool:
```
Installing tools:

  create-docs...        done
  codebase-health...    done
  debug-triage...       done
  update-backlog...     done
```

**Error handling:** If a tool's install.sh fails (non-zero exit code):
- Report the error: `create-docs...  FAILED (exit code 1)`
- Capture and display stderr
- Continue with remaining tools (do not abort the entire install)
- Track failed tools for the summary

Each tool's `install.sh` handles all file copying, sed placeholder resolution, workspace scaffolding, and manifest update internally.

---

## Step 7: Post-Install Validation

Run validation on the target:

```bash
python3 "$MG_INSTALL_LIB" validate --target "$TARGET_PATH"
```

This returns JSON with: `issues` array and `valid` boolean.

**Display results:**

If valid:
```
Post-install validation:
  All checks passed -- no unresolved placeholders, all paths valid
```

If issues found:
```
Post-install validation:

  WARNING: Unresolved placeholder in create-docs-verify.md: {SCRIPTS_DIR}
  WARNING: Missing path referenced in codebase-health.md: /old/path/to/scripts

  2 validation issues found. These are warnings -- the install completed,
  but affected tools may not function correctly until issues are resolved.
```

Validation issues are **warnings** (the install already happened). Display them so the user is aware.

---

## Step 8: Summary

Format and display the final summary:

```
mg-cc-tools -- INSTALL COMPLETE

  Target: /home/user/projects/road-runner

  Installed: 3  |  Updated: 2  |  Unchanged: 4  |  Skipped: 2

  Tool                Action       Commands
  ------------------------------------------------
  create-docs         Updated      5 commands
  codebase-health     Installed    4 commands
  debug-triage        Installed    1 command
  update-backlog      Installed    1 command
  create-context      Updated      2 commands
  permission-hooks    Unchanged    --
  mg-gsd-wrappers     Unchanged    --
  gsd-patches         Unchanged    --

  Capabilities:
    LSP: functional (python, javascript)
    Missing optional tools: ruff, vulture (codebase-health scan degraded)

  Manifest: .claude/mg-cc-tools.manifest.json
```

**Action column values:**
- `Installed` -- newly installed this run
- `Updated` -- reinstalled due to version or source changes
- `Unchanged` -- already current, not reinstalled
- `Failed` -- install.sh failed (show error details above)

After displaying the summary, update `~/.config/mg-cc-tools/targets.json` with this target (if not already done in Step 1).

---

## Key Constraints

1. **Always runs from mg-cc-tools directory** -- source is always `./`
2. **mg-install-lib.py is at `./install/scripts/mg-install-lib.py`** -- no sed resolution needed since this command always runs from the source directory
3. **AskUserQuestion is ONLY for target selection** (Step 1) -- action selection (Step 3) uses numbered text prompts parsed by the LLM
4. **claude -p probe runs from the TARGET directory** -- LSP availability is project-specific
5. **Excluded tools** (install, cc-regression-test) are shown in status but excluded from bulk operations; they can be installed explicitly by name
6. **Each tool's install.sh handles its own manifest update** -- this command does NOT call update-manifest directly
7. **Preflight required check failure is a hard abort** -- do not proceed to installation
8. **LSP probe failure is never blocking** -- note it and continue
