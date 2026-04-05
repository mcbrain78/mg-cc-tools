# Auto-Doc -- Post-Install Configuration

<objective>
Add Write permissions for auto-doc workspace paths to the target project's settings.local.json.
Auto-doc subagents (scan, generate, verify) need Write access to `.mg/` (temp files, scan output, config)
and `docs/auto-doc/` (generated documentation) without interactive approval prompts.
</objective>

<context>
The target project path and source directory path are provided at the top of this prompt.
Use "the target project" and "the source directory" to reference these paths throughout.

- Target project: The project where the tool is being installed
- Source directory: The mg-cc-tools repository root
</context>

<process>

## Step 1: Resolve Target Project

The target project path is provided at the top of this prompt. No argument parsing is needed.

Set derived variables:
- `TARGET_SETTINGS_LOCAL` = `<target project>/.claude/settings.local.json`

Validate that the target project directory exists:
```bash
ls -d "<target project>" 2>/dev/null
```
If not found, output:
> POST-INSTALL: FAILED: Target project not found

Stop.

## Step 2: Configure Permissions and Gitignore

Run the post-install configuration script. It handles both permissions and .gitignore in a single call:

```bash
python3 {MG_INSTALL_SCRIPTS_DIR}/post-install-configure.py \
    --project-root "<target project>" \
    --settings-path "<TARGET_SETTINGS_LOCAL>"
```

The script:
- Adds `Write(path:.mg/)` and `Write(path:docs/auto-doc/)` to settings.local.json (idempotent)
- Ensures `.mg/` is in `.gitignore` (idempotent)
- Prints `permissions=ADDED` or `permissions=OK` and `gitignore=ADDED` or `gitignore=OK`

## Step 3: Status Report

```
Auto-Doc Permissions
==================================================

  Target:      <target project>
  Settings:    <TARGET_SETTINGS_LOCAL>
  Permissions: [ADDED / OK]

  Write(path:.mg/)           — workspace, temp files, scan output
  Write(path:docs/auto-doc/) — generated documentation
  .gitignore:                [ADDED / OK] .mg/ entry

==================================================
```

</process>

<completion>

Output exactly ONE of these markers as the final line:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
