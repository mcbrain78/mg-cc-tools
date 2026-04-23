# Transcript Tools -- Post-Install Configuration

<objective>
Register the inject-transcript-path.py PreToolUse hook in settings.json.
The hook auto-injects `--transcript <path>` into exporter commands so the LLM
does not need to resolve session IDs.  install.sh copies the hook file;
this step handles JSON merging into settings.json.
</objective>

<context>
The target project path, source directory path, and install mode are provided at the top of this prompt.

- Target project: The project where the tool is being installed
- Source directory: The mg-cc-tools repository root
- Install mode: `project` (default), `global`, or `target`. In `project` mode the hook command emitted into settings.json uses a relative path so the entry is portable across clones. In `global`/`target` mode an absolute path is baked in.
</context>

<process>

## Step 1: Resolve Paths

Set derived variables:
- `TARGET_CLAUDE` = `<target project>/.claude`
- `TARGET_HOOK` = `<TARGET_CLAUDE>/transcript/hooks/inject-transcript-path.py`
- `TARGET_SETTINGS` = `<TARGET_CLAUDE>/settings.json`
- `INSTALL_MODE` = value of the `Install mode:` line from the top of the prompt (default `project`)

Validate the hook file was copied by install.sh:
```bash
ls "<TARGET_HOOK>" 2>/dev/null
```

If not found, output:
> POST-INSTALL: FAILED: Hook file not found at <TARGET_HOOK> — run install.sh first

Stop.

## Step 2: Register Hook in settings.json

Check if the PreToolUse hook entry for inject-transcript-path.py exists in settings.json.

The hook needs exactly 1 matcher: `Bash`. It must be registered as its own entry in the
`PreToolUse` array — NOT added to an existing Bash matcher's `hooks` list (Claude Code
only runs the first command in a `hooks` list).

```bash
python3 -c "
import json, sys

hook_path = '<TARGET_HOOK>'
settings_path = '<TARGET_SETTINGS>'
install_mode = '<INSTALL_MODE>'  # 'project' | 'global' | 'target'

if install_mode == 'project':
    hook_cmd = 'python3 .claude/transcript/hooks/inject-transcript-path.py'
else:
    hook_cmd = 'python3 ' + hook_path

try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

hooks = settings.setdefault('hooks', {})
pre_tool = hooks.setdefault('PreToolUse', [])

# Check if already registered (in any entry's hooks list)
already = any(
    isinstance(entry, dict)
    and entry.get('matcher') == 'Bash'
    and any(
        isinstance(hk, dict) and hook_path in hk.get('command', '')
        for hk in entry.get('hooks', [])
    )
    for entry in pre_tool
)

if already:
    print('OK: Hook already registered in ' + settings_path)
else:
    new_entry = {
        'matcher': 'Bash',
        'hooks': [{'type': 'command', 'command': hook_cmd}]
    }
    pre_tool.append(new_entry)
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    print('ADDED: PreToolUse Bash hook entry for inject-transcript-path.py')
"
```

**If ADDED:** Report that the hook was registered.

**If OK:** Report that the hook is already configured.

</process>

<completion>
## Status

After all steps complete, output a final summary:

```
Transcript Hook Status
==================================================

  Target:     <target project>
  Hook file:  <TARGET_HOOK>
  Settings:   [ADDED / OK]

==================================================
```

If the hook was just added, remind the user:
> Note: Restart Claude Code in the target project for hook changes to take effect.

Then output exactly ONE of these markers as the final line:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
