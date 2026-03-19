# Permission Hooks -- Post-Install Configuration

<objective>
Install the permission-guard hook into the target project and register it in settings.json.
This step requires Claude Code intelligence for JSON merging (settings.json hook entry management),
sync checking with user prompts, and smoke testing -- tasks that cannot be done by simple file copies.
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
- `TARGET_CLAUDE` = `<target project>/.claude`
- `TARGET_HOOKS_DIR` = `<TARGET_CLAUDE>/permission-hooks/hooks`
- `TARGET_SETTINGS` = `<TARGET_CLAUDE>/settings.json`

Validate that the target project directory exists:
```bash
ls -d "<target project>" 2>/dev/null
```
If not found, output:
> POST-INSTALL: FAILED: Target project not found

Stop.

## Step 2: Install / Sync Hook File

Check if the hook is already installed in the target:

```bash
ls "<TARGET_HOOKS_DIR>/permission-guard.py" 2>/dev/null
```

### If not installed (fresh install):

1. Create the directory and copy the hook from the source directory's `permission-hooks/hooks/permission-guard.py`:
```bash
mkdir -p "<TARGET_HOOKS_DIR>"
cp "<source directory>/permission-hooks/hooks/permission-guard.py" "<TARGET_HOOKS_DIR>/permission-guard.py"
chmod +x "<TARGET_HOOKS_DIR>/permission-guard.py"
```

2. Resolve the `{PROJECT_ROOT}` placeholder -- replace with the absolute path to the target project:
```bash
sed -i "s|{PROJECT_ROOT}|<target project>|g" "<TARGET_HOOKS_DIR>/permission-guard.py"
```

Log: `Installed permission-guard.py to <TARGET_HOOKS_DIR>/`

### If already installed (sync check):

Compare the installed hook (ignoring the PROJECT_ROOT line) against the source:

```bash
# Compare ignoring the PROJECT_ROOT assignment line
INSTALLED_MD5=$(grep -v '^PROJECT_ROOT = ' "<TARGET_HOOKS_DIR>/permission-guard.py" | md5sum | cut -d' ' -f1)
SOURCE_MD5=$(grep -v '^PROJECT_ROOT = ' "<source directory>/permission-hooks/hooks/permission-guard.py" | md5sum | cut -d' ' -f1)
echo "installed: $INSTALLED_MD5"
echo "source:    $SOURCE_MD5"
```

**If identical:** Log `Hook file in sync.` and proceed to Step 3.

**If different:** Ask via AskUserQuestion:
- header: "Sync"
- question: "Installed permission-guard.py is out of sync with source. Sync now?"
- options:
  - "Sync now" -- "Copy updated hook from source"
  - "Continue stale" -- "Proceed with currently installed hook"

**If "Sync now":**

1. Read the currently installed file to extract the resolved PROJECT_ROOT value
2. Copy the source file over:
```bash
cp "<source directory>/permission-hooks/hooks/permission-guard.py" "<TARGET_HOOKS_DIR>/permission-guard.py"
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
  - "Fix" -- "Update the command path in settings.json"
  - "Skip" -- "Leave as-is"

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
print('Permission Guard -- Rule Categories:')
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

</process>

<completion>
## Status

After all steps complete, output a final summary:

```
Permission Guard Status
==================================================

  Target:     <target project>
  Hook file:  <TARGET_HOOKS_DIR>/permission-guard.py
  Settings:   [ADDED / OK / MISMATCH]
  Sync:       [Fresh install / In sync / Synced / Stale]
  Smoke test: [PASS / FAIL]

==================================================
```

If the hook was just added or synced, remind the user:
> Note: Restart Claude Code in the target project for hook changes to take effect.

Then output exactly ONE of these markers as the final line:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
