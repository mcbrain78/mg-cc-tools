# Install Permission Hooks

---
name: mg:install-permission-hooks
description: Install and manage the permission-guard PreToolUse hook in a target project
argument-hint: "<project-name-or-path>"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

<objective>
Install the permission-guard hook into a target project and register it in settings.json.
Handles file copying, PROJECT_ROOT resolution, settings.json management, sync checking,
status reporting, and smoke testing — all in one command.
</objective>

<context>
Target project argument: $ARGUMENTS

Source directory: /home/mcbrain/mg_projects/mg-cc-tools/permission-hooks
</context>

<process>

## Step 1: Resolve Target Project

The argument `$ARGUMENTS` is either:
- A **project name** (e.g., `road-runner`) — resolve as a sibling directory of mg-cc-tools
- An **absolute path** (starts with `/`) — use directly
- **Empty** — install into the current project (mg-cc-tools itself)

**Resolution logic:**
1. If `$ARGUMENTS` is empty, use the current project root (parent of `.claude/` where this command is installed). Derive from `/home/mcbrain/mg_projects/mg-cc-tools/permission-hooks`: go up one level from the source directory to get the mg-cc-tools root, that's the target.
2. If `$ARGUMENTS` starts with `/`, use it as-is → `TARGET_PROJECT=$ARGUMENTS`
3. Otherwise, resolve as sibling: find the mg-cc-tools root from `/home/mcbrain/mg_projects/mg-cc-tools/permission-hooks` (go up one level), then go up one more level, and append the project name → `TARGET_PROJECT=<parent>/<name>`

**Validate:** Check that the target project directory exists:
```bash
ls -d "<TARGET_PROJECT>" 2>/dev/null
```
If not found:
> "Target project not found: `<TARGET_PROJECT>`."

Stop.

Set derived variables:
- `TARGET_CLAUDE` = `<TARGET_PROJECT>/.claude`
- `TARGET_HOOKS_DIR` = `<TARGET_CLAUDE>/permission-hooks/hooks`
- `TARGET_SETTINGS` = `<TARGET_CLAUDE>/settings.json`

## Step 2: Install / Sync Hook File

Check if the hook is already installed in the target:

```bash
ls "<TARGET_HOOKS_DIR>/permission-guard.py" 2>/dev/null
```

### If not installed (fresh install):

1. Create the directory and copy the hook:
```bash
mkdir -p "<TARGET_HOOKS_DIR>"
cp "/home/mcbrain/mg_projects/mg-cc-tools/permission-hooks/hooks/permission-guard.py" "<TARGET_HOOKS_DIR>/permission-guard.py"
chmod +x "<TARGET_HOOKS_DIR>/permission-guard.py"
```

2. Resolve `{PROJECT_ROOT}` placeholder — replace with the absolute path to `TARGET_PROJECT`:
```bash
sed -i "s|{PROJECT_ROOT}|<TARGET_PROJECT>|g" "<TARGET_HOOKS_DIR>/permission-guard.py"
```

Log: `Installed permission-guard.py to <TARGET_HOOKS_DIR>/`

### If already installed (sync check):

Compare the installed hook (ignoring the PROJECT_ROOT line) against the source:

```bash
# Compare ignoring the PROJECT_ROOT assignment line
INSTALLED_MD5=$(grep -v '^PROJECT_ROOT = ' "<TARGET_HOOKS_DIR>/permission-guard.py" | md5sum | cut -d' ' -f1)
SOURCE_MD5=$(grep -v '^PROJECT_ROOT = ' "/home/mcbrain/mg_projects/mg-cc-tools/permission-hooks/hooks/permission-guard.py" | md5sum | cut -d' ' -f1)
echo "installed: $INSTALLED_MD5"
echo "source:    $SOURCE_MD5"
```

**If identical:** Log `Hook file in sync.` and proceed to Step 3.

**If different:** Ask via AskUserQuestion:
- header: "Sync"
- question: "Installed permission-guard.py is out of sync with source. Sync now?"
- options:
  - "Sync now" — "Copy updated hook from source"
  - "Continue stale" — "Proceed with currently installed hook"

**If "Sync now":**

1. Read the currently installed file to extract the resolved PROJECT_ROOT value
2. Copy the source file over:
```bash
cp "/home/mcbrain/mg_projects/mg-cc-tools/permission-hooks/hooks/permission-guard.py" "<TARGET_HOOKS_DIR>/permission-guard.py"
chmod +x "<TARGET_HOOKS_DIR>/permission-guard.py"
```
3. Re-resolve PROJECT_ROOT with the previously extracted value:
```bash
sed -i "s|{PROJECT_ROOT}|<extracted-project-root>|g" "<TARGET_HOOKS_DIR>/permission-guard.py"
```

Log: `Hook synced from source.`

## Step 3: Settings.json Management

Check if the PreToolUse hook entries for permission-guard.py exist in the target's settings.json.

The hook needs 4 matchers: `Bash`, `Read`, `Edit`, `Write`. The same Python script handles all tool types.

```bash
python3 -c "
import json, os, sys

hooks_dir = '<TARGET_HOOKS_DIR>'
settings_path = '<TARGET_SETTINGS>'

hook_cmd = 'python3 ' + os.path.join(hooks_dir, 'permission-guard.py')

try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

hooks = settings.setdefault('hooks', {})
pre_tool = hooks.setdefault('PreToolUse', [])

matchers = ['Bash', 'Read', 'Edit', 'Write']
added = []
ok = []

for matcher in matchers:
    new_entry = {
        'matcher': matcher,
        'hooks': [{'type': 'command', 'command': hook_cmd}]
    }

    # Check if already present for this matcher
    already = any(
        isinstance(h, dict)
        and h.get('matcher') == matcher
        and any(
            isinstance(hk, dict) and hk.get('command') == hook_cmd
            for hk in h.get('hooks', [])
        )
        for h in pre_tool
    )

    if not already:
        pre_tool.append(new_entry)
        added.append(matcher)
    else:
        ok.append(matcher)

if added:
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    print('ADDED: Hook entries added for matchers: ' + ', '.join(added))
    if ok:
        print('OK: Already present for matchers: ' + ', '.join(ok))
else:
    print('OK: All hook entries present and correct in ' + settings_path)
"
```

**If ADDED:** Report that the hook was added.

**If OK:** Report that the hook is correctly configured.

**If MISMATCH:** Ask via AskUserQuestion:
- header: "Fix path"
- question: "Hook entry exists but points to wrong path. Fix it?"
- options:
  - "Fix" — "Update the command path in settings.json"
  - "Skip" — "Leave as-is"

If "Fix": Update the command path in settings.json using a similar Python snippet that removes the old entry and adds the correct one.

## Step 4: Status Report

Read the installed permission-guard.py and extract category information.

```bash
python3 -c "
import sys, os
sys.path.insert(0, '<TARGET_HOOKS_DIR>')
import importlib
guard = importlib.import_module('permission-guard')

total = 0
print('Permission Guard — Rule Categories:')
print('=' * 50)
for cat, patterns in guard.CATEGORIES.items():
    count = len(patterns)
    total += count
    print(f'  {cat}: {count} rules')
print('=' * 50)
print(f'  Total: {total} rules + out-of-project path guard')
print()
print(f'  PROJECT_ROOT: {guard.PROJECT_ROOT!r}')
if not guard.PROJECT_ROOT or guard.PROJECT_ROOT == '{' + 'PROJECT_ROOT' + '}':
    print('  (will fall back to cwd from hook event)')
"
```

## Step 5: Smoke Test

Pipe a known-dangerous command through the hook to verify it works:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"sudo rm -rf /"}}' | python3 "<TARGET_HOOKS_DIR>/permission-guard.py"
```

**If output contains `"permissionDecision": "ask"`:** Report `Smoke test: PASS`

**If no output or unexpected output:** Report `Smoke test: FAIL` and show what was returned.

## Completion

```
══════════════════════════════════════════════
  Permission Guard Status
══════════════════════════════════════════════

  Target:     <TARGET_PROJECT>
  Hook file:  <TARGET_HOOKS_DIR>/permission-guard.py
  Settings:   [ADDED / OK / MISMATCH]
  Sync:       [Fresh install / In sync / Synced / Stale]
  Smoke test: [PASS / FAIL]

══════════════════════════════════════════════
```

If the hook was just added or synced, remind the user:

```
Note: Restart Claude Code in the target project for hook changes to take effect.
```

</process>

<important_notes>
- This command both installs AND manages the hook — no separate install.sh needed for target projects.
- Hook changes require a Claude Code restart in the target project to take effect.
- The smoke test validates that the Python script processes input correctly, but doesn't test the actual hook integration (that requires a real Bash command in a running session).
- The sync check ignores the PROJECT_ROOT line since it's always different between source and installed copies.
- For project name arguments, resolution follows the same sibling-directory pattern as mg:apply-gsd-patches.
</important_notes>
