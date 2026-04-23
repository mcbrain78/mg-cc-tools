# CC Regression Test -- Post-Install Configuration

<objective>
Merge the PreToolUse hook entry for intercept-trigger.py into the target project's
settings.json. This step requires Claude Code intelligence for JSON merging with
edge case handling (missing file, missing keys, idempotent updates) that cannot be
done by simple file copies in install.sh.
</objective>

<context>
The target project path, source directory path, and install mode are provided at the top of this prompt.

- Target project: The project where the tool is being installed
- Source directory: The mg-cc-tools repository root
- Install mode: `project` (default), `global`, or `target`. In `project` mode the hook command emitted into settings.json uses a relative path so the entry is portable across clones. In `global`/`target` mode an absolute path is baked in.
</context>

<process>

## Step 1: Determine Paths

Set these paths based on the target project:
- `INSTALL_MODE` = value of the `Install mode:` line (default `project`)
- Hook command:
  - In `project` mode: `python3 .claude/cc-regression-test/hooks/intercept-trigger.py`
  - Otherwise: `python3 <target project>/.claude/cc-regression-test/hooks/intercept-trigger.py`
- Settings file: `<target project>/.claude/settings.json`

Validate that the hook file was installed by install.sh:
```bash
ls "<target project>/.claude/cc-regression-test/hooks/intercept-trigger.py" 2>/dev/null
```

If not found, output:
> POST-INSTALL: FAILED: Hook file not found at expected location -- install.sh may have failed

Stop.

## Step 2: Read Existing Settings

Read the target project's settings.json. Handle three cases:
- **File does not exist:** Start with an empty settings object `{}`
- **File exists but has no `hooks` key:** Add it
- **File exists with `hooks` but no `PreToolUse` array:** Add it

```bash
python3 -c "
import json, os, sys

settings_path = '<target project>/.claude/settings.json'
install_mode = '<INSTALL_MODE>'  # 'project' | 'global' | 'target'
if install_mode == 'project':
    hook_cmd = 'python3 .claude/cc-regression-test/hooks/intercept-trigger.py'
else:
    hook_cmd = 'python3 <target project>/.claude/cc-regression-test/hooks/intercept-trigger.py'

# Read or create settings
try:
    with open(settings_path) as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}
except json.JSONDecodeError:
    print('WARNING: settings.json exists but is not valid JSON. Creating backup.')
    import shutil
    shutil.copy2(settings_path, settings_path + '.bak')
    settings = {}

# Ensure structure exists
hooks = settings.setdefault('hooks', {})
pre_tool = hooks.setdefault('PreToolUse', [])

# Step 3: Check if entry already present (idempotent)
already = any(
    isinstance(h, dict)
    and h.get('matcher') == 'Bash'
    and any(
        isinstance(hk, dict) and hk.get('command') == hook_cmd
        for hk in h.get('hooks', [])
    )
    for h in pre_tool
)

if already:
    print('OK: Hook entry already present in settings.json')
else:
    # Step 4: Append the entry
    new_entry = {
        'matcher': 'Bash',
        'hooks': [{'type': 'command', 'command': hook_cmd}]
    }
    pre_tool.append(new_entry)

    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    print('ADDED: Hook entry for intercept-trigger.py added to settings.json')

# Step 5: Report
print()
print('Settings file: ' + settings_path)
print('Hook command:  ' + hook_cmd)
print('Matcher:       Bash')
"
```

</process>

<completion>
## Status

After all steps complete, output exactly ONE of these markers as the final line:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
