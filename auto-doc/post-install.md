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

## Step 2: Add Write Permissions

Add the required permission entries to settings.local.json. These allow auto-doc subagents
to write temp files, scan output, and generated docs without interactive approval.

Required permissions:
- `Write(path:.mg/)` — workspace temp files, scan logs, docs-scan.json, reference manifests, config
- `Write(path:docs/auto-doc/)` — generated documentation output

```bash
python3 -c "
import json, os

settings_path = '<TARGET_SETTINGS_LOCAL>'

try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

perms = settings.setdefault('permissions', {})
allow = perms.setdefault('allow', [])

needed = [
    'Write(path:.mg/)',
    'Write(path:docs/auto-doc/)',
]

added = []
for perm in needed:
    if perm not in allow:
        allow.append(perm)
        added.append(perm)

if added:
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    print('ADDED: ' + ', '.join(added))
else:
    print('OK: All permissions already present')
"
```

**If ADDED:** Report which permissions were added.

**If OK:** Report that permissions are correctly configured.

## Step 3: Ensure .mg is in .gitignore

Check if `.mg` (or `.mg/`) is already in the target project's `.gitignore`. If not, append it.

```bash
python3 -c "
import os

gitignore_path = '<target project>/.gitignore'
patterns = ['.mg', '.mg/']

try:
    with open(gitignore_path) as f:
        lines = f.read().splitlines()
except FileNotFoundError:
    lines = []

already_present = any(line.strip() in patterns for line in lines)

if already_present:
    print('OK: .mg already in .gitignore')
else:
    with open(gitignore_path, 'a') as f:
        if lines and lines[-1] != '':
            f.write('\n')
        f.write('.mg/\n')
    print('ADDED: .mg/ to .gitignore')
"
```

## Step 4: Status Report

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
