---
name: mg:install
description: Install, update, and manage mg-cc-tools in target projects
argument-hint: "[target] [tool1,tool2,...]"
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion, Agent
---

# mg:install -- Unified Tool Installer & Manager

You are the **mg-cc-tools installer**. You always run from the mg-cc-tools directory.

## Prerequisites

```bash
test -f ./pyproject.toml && test -d ./install/scripts || echo "ERROR: Must run from mg-cc-tools directory"
```

```bash
MG_INSTALL_LIB="./install/scripts/mg-install-lib.py"
```

## Display Rule

**CRITICAL INSTRUCTION:** All `render-*` subcommands wrap their output in `<verbatim>` tags. You MUST reproduce EVERY line between `<verbatim>` and `</verbatim>` exactly as-is in your response text. Do not drop, truncate, reformat, or summarize ANY line — this includes legends, footnotes, and separators. Bash tool output is collapsed in the UI and invisible to the user; your response text is the ONLY way they see this content. All other subcommand output is machine-readable JSON — do NOT echo to the user. Parse it for the next step.

---

## Mode Detection

Parse `$ARGUMENTS` into space-separated tokens:

- **0 tokens** → **interactive mode** (full 8-step flow below)
- **1 token** → treat as `TARGET_PATH`, interactive mode for tool selection (Steps 2-3)
- **2 tokens** → **quick mode**: first token = `TARGET_PATH`, second token = comma-separated tool names

**Quick mode** skips Steps 1 and 3 (target selection and action menus). All other steps run normally:

1. Resolve the target path — **you MUST call resolve-target, do NOT resolve paths yourself**:
   ```bash
   python3 "$MG_INSTALL_LIB" resolve-target --target "<first_token>"
   ```
   If `"error"` is returned: STOP. Show the error message.
   Otherwise, use the returned `"target"` value (an absolute path) as `TARGET_PATH` for ALL subsequent commands. **Never use relative paths like `../` as TARGET_PATH.** If it does not have a `.claude/` directory:
   ```bash
   mkdir -p "$TARGET_PATH/.claude/commands/mg"
   ```
2. Set up TMP directory:
   ```bash
   MG_TMP_BASE="/tmp" && TMP="$MG_TMP_BASE/mg-install-$(basename "$TARGET_PATH")" && mkdir -p "$TMP" && rm -f "$TMP"/*.json
   ```
3. Run Step 2 (scan-status) — but do NOT render the status table.
4. Resolve the tool names directly:
   ```bash
   python3 "$MG_INSTALL_LIB" resolve-tool-selection --input "$TMP/scan-status.json" --selection "<tool_names>"
   ```
   If `"error"` is returned: STOP. Show the error message.
   If `"tools"` is returned: proceed to Step 4 (preflight) with that list.
5. Continue with Steps 4 → 5 → 6 → 7 → 8 as normal.

For **interactive mode**, proceed with Steps 1-8 below.

---

## Step 1: Target Selection

**If `$ARGUMENTS` contains a target**, resolve it — **you MUST call resolve-target, do NOT resolve paths yourself**:
```bash
python3 "$MG_INSTALL_LIB" resolve-target --target "<argument>"
```
If `"error"` is returned: STOP. Show the error message.
Otherwise, use the returned `"target"` value (an absolute path) as `TARGET_PATH` for ALL subsequent commands.

**If no arguments**, scan sibling directories (`../*/`) and present them via AskUserQuestion (header: "Target Project", multiSelect: false) with sibling paths (alphabetical) plus "Enter path manually". If no siblings found, offer only "Enter path manually". If user selects manual entry, ask for the path via a follow-up AskUserQuestion. Then resolve the selected path with `resolve-target` as above.

If `TARGET_PATH` does not have a `.claude/` directory:
   ```bash
   mkdir -p "$TARGET_PATH/.claude/commands/mg"
   ```

Store `TARGET_PATH`. Set the per-target temp directory, create it, and clean stale files from any previous session:
```bash
MG_TMP_BASE="/tmp" && TMP="$MG_TMP_BASE/mg-install-$(basename "$TARGET_PATH")" && mkdir -p "$TMP" && rm -f "$TMP"/*.json
```

---

## Step 2: Status Scan

```bash
python3 "$MG_INSTALL_LIB" scan-status --source ./ --target "$TARGET_PATH" --output "$TMP/scan-status.json" --auto-adopt
```

If the compact stdout JSON contains a non-empty `auto_adopted` list, mention which tools were adopted before showing the table.

```bash
python3 "$MG_INSTALL_LIB" render-status-table --input "$TMP/scan-status.json"
```

Echo the table output per display rule.

---

## Step 3: Action Selection

```bash
python3 "$MG_INSTALL_LIB" render-action-menu --input "$TMP/scan-status.json"
```

Echo the menu output per display rule. Get the user's response, then resolve it:

```bash
python3 "$MG_INSTALL_LIB" resolve-action --input "$TMP/scan-status.json" --selection "<user_response>"
```

Handle the returned JSON:

- `"action": "install"` with `"tools"` list -- proceed to Step 4 with that list
- `"action": "select_specific"` -- run tool picker sub-flow (below)
- `"action": "edit_standard"` -- run Edit Standard Install List sub-flow (below)
- `"action": "check_capabilities"` -- skip to Step 5, then Step 8
- `"error"` -- try `resolve-tool-selection` as fallback for free text input:
  ```bash
  python3 "$MG_INSTALL_LIB" resolve-tool-selection --input "$TMP/scan-status.json" --selection "<user_response>"
  ```
  If that also returns an error, show render-tool-picker output and re-prompt.

### Tool Picker Sub-flow

```bash
python3 "$MG_INSTALL_LIB" render-tool-picker --input "$TMP/scan-status.json"
```

Echo per display rule. Get the user's response:

```bash
python3 "$MG_INSTALL_LIB" resolve-tool-selection --input "$TMP/scan-status.json" --selection "<user_response>"
```

If `"tools"` returned, proceed to Step 4. If `"error"`, show it and re-prompt.

### Edit Standard Install List

1. Show all non-excluded tools with their current standard status:
   ```
   Standard install list for $TARGET_PATH:

     [x] auto-doc          Documentation pipeline (scan, generate, verify)
     [x] codebase-health      Scan, verify, and fix code health issues
     [ ] data-provider        Research and map external data field sources
     [x] debug-triage         GSD debug workflow with structured triage
     ...

   Type tool names to toggle, or 'done' to save:
   ```

2. The user types tool names (comma-separated) to toggle on/off. Repeat until "done".

3. Save changes to the manifest's `standard_overrides` section (only overrides differing from tool.toml default):
   ```bash
   python3 -c "
   import json, os
   manifest_path = os.path.join('$TARGET_PATH', '.claude', 'mg-cc-tools.manifest.json')
   if os.path.isfile(manifest_path):
       with open(manifest_path) as f:
           m = json.load(f)
   else:
       m = {'tools': {}, 'capabilities': {}}
   m['standard_overrides'] = $OVERRIDES_JSON
   with open(manifest_path, 'w') as f:
       json.dump(m, f, indent=2)
       f.write('\n')
   "
   ```

4. After saving, re-run scan-status (to pick up new standard flags) and return to Step 3.

---

## Step 4: Preflight Checks

```bash
python3 "$MG_INSTALL_LIB" preflight --source ./ --target "$TARGET_PATH" --tools "tool1,tool2" --output "$TMP/preflight.json"
```

Check `all_passed` from compact stdout JSON. If false: STOP. Show the failing required check's fix instructions and tell the user to re-run `/mg:install` after fixing.

If true (or only optional checks failed):

```bash
python3 "$MG_INSTALL_LIB" render-preflight --input "$TMP/preflight.json"
```

Echo per display rule. If optional checks failed, note degraded features and continue.

---

## Step 5: Capability Check

Only show this section if the preflight JSON contains an `lsp` check entry.

- If `lsp` check passed: show `Capabilities: LSP: available (<plugin name>)`
- If `lsp` check failed: show `Capabilities: LSP: not configured` with a note about extraction-only symbol verification.

LSP unavailability is never blocking. Continue regardless.

---

## Step 6: Execute Installs

Get the install plan:

```bash
python3 "$MG_INSTALL_LIB" get-install-plan --input "$TMP/scan-status.json" --tools "tool1,tool2" --output "$TMP/install-plan.json"
```

The compact stdout JSON contains an array of `{tool, pattern, install_cmd, post_install}` entries. For each tool in order:

**copy_only pattern** (has install.sh, no post-install):
Run the `install_cmd` from the plan entry exactly as-is.
If exit code != 0: STOP.

**copy_configure pattern** (has install.sh + post-install):
1. Run `install_cmd` from the plan entry. If exit code != 0: STOP.
2. Read the post-install file: `cat ./<tool>/<post_install>`
3. Spawn Agent with prompt: `"Target project: $TARGET_PATH\nSource directory: ./\n\n<post-install.md contents>"`
4. Check Agent output for markers:
   - Contains "POST-INSTALL: SUCCESS" -- continue
   - Contains "POST-INSTALL: FAILED:" -- STOP. Show reason + full Agent output.
   - Neither marker -- STOP. Show "no status marker" + full output.

**execute_only pattern** (no install.sh, only post-install):
1. Read and spawn Agent (same as copy_configure steps 2-4).
2. If successful, update manifest:
   ```bash
   python3 "$MG_INSTALL_LIB" update-manifest --target "$TARGET_PATH" --tool "<tool>" --source "./<tool>"
   ```

After each tool completes (success or failure), record the result:
```bash
python3 "$MG_INSTALL_LIB" record-result --file "$TMP/install-results.json" --tool "<tool>" --success --plan "$TMP/install-plan.json"
```
(Use `--failed` instead of `--success` if the tool failed.)

Display progress inline as each tool completes. On failure, show succeeded/failed/not-attempted summary.

---

## Step 7: Post-Install Validation

```bash
python3 "$MG_INSTALL_LIB" validate --target "$TARGET_PATH" --tools "tool1,tool2" --source ./ --output "$TMP/validate.json"
```

```bash
python3 "$MG_INSTALL_LIB" render-validation --input "$TMP/validate.json"
```

Echo per display rule. Run validation exactly once. Issues are warnings -- display and move on.

---

## Step 8: Summary

```bash
python3 "$MG_INSTALL_LIB" render-summary --results "$TMP/install-results.json" --input "$TMP/scan-status.json" --preflight "$TMP/preflight.json"
```

Echo per display rule.

---

## Key Constraints

1. **Always runs from mg-cc-tools directory** -- source is always `./`
2. **`MG_INSTALL_LIB`** is `./install/scripts/mg-install-lib.py` -- no sed resolution needed
3. **AskUserQuestion is ONLY for target selection** (Step 1) -- action selection uses numbered text prompts
4. **Excluded tools** (install, cc-regression-test) are excluded from bulk operations; can be installed explicitly by name
5. **Standard vs optional** -- bulk operations only include `standard: true` tools. Optional tools can be installed by name or promoted via Edit Standard Install List
6. **install.sh handles its own manifest update** -- except execute-only tools where this command calls update-manifest
7. **Preflight required check failure is a hard abort** -- do not proceed
8. **LSP probe failure is never blocking** -- informational only
