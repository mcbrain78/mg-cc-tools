# Permission Hooks -- Post-Install Configuration

<objective>
Install the permission-guard hook into the target project and register it in settings.json.
This step requires Claude Code intelligence for JSON merging (settings.json hook entry management),
sync checking with user prompts, and smoke testing -- tasks that cannot be done by simple file copies.
</objective>

<context>
The target project path, source directory path, and install mode are provided at the top of this prompt.
Use "the target project" and "the source directory" to reference these paths throughout.

- Target project: The project where the tool is being installed
- Source directory: The mg-cc-tools repository root
- Install mode: `project` (default when invoked via the install.md orchestrator),
  `global`, or `target`. In `project` mode, paths emitted into settings.json and
  the hook file's PROJECT_ROOT are kept portable (relative / unresolved
  placeholder). In `global`/`target` mode, absolute paths are baked in.
</context>

<process>

## Step 1: Resolve Target Project

The target project path is provided at the top of this prompt. No argument parsing is needed.

Set derived variables:
- `TARGET_CLAUDE` = `<target project>/.claude`
- `TARGET_HOOKS_DIR` = `<TARGET_CLAUDE>/permission-hooks/hooks`
- `TARGET_SETTINGS` = `<TARGET_CLAUDE>/settings.json`
- `INSTALL_MODE` = value of the `Install mode:` line from the top of the prompt
  (default to `project` if not present)

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

2. Resolve the `{MG_INSTALL_PROJECT_ROOT}` placeholder:
   - **If `INSTALL_MODE == project`:** leave the placeholder in place. At runtime the hook's `_resolve_project_root()` helper detects the `{` prefix and falls back to `event.cwd`, so the hook works in any clone of the project.
   - **Otherwise (global/target):** replace with the absolute path to the target project:
     ```bash
     sed -i "s|{MG_INSTALL_PROJECT_ROOT}|<target project>|g" "<TARGET_HOOKS_DIR>/permission-guard.py"
     ```

Log: `Installed permission-guard.py to <TARGET_HOOKS_DIR>/`

### If already installed (copy verification):

Compare the installed hook (ignoring the PROJECT_ROOT line) against the source:

```bash
# Compare ignoring the PROJECT_ROOT assignment line
INSTALLED_MD5=$(grep -v '^PROJECT_ROOT = ' "<TARGET_HOOKS_DIR>/permission-guard.py" | md5sum | cut -d' ' -f1)
SOURCE_MD5=$(grep -v '^PROJECT_ROOT = ' "<source directory>/permission-hooks/hooks/permission-guard.py" | md5sum | cut -d' ' -f1)
echo "installed: $INSTALLED_MD5"
echo "source:    $SOURCE_MD5"
```

**Read this as an integrity check on the copy, not as drift detection.** When invoked
by the `/mg:install` orchestrator, `install.sh` has already copied the hook into the
target before this step runs, so the comparison is between the source and a copy just
made from it. A match therefore proves the copy landed intact — not truncated, and not
mangled by placeholder substitution. It says nothing about what the target held
beforehand, and must never be reported as "the target was already current."

The one place that question is answerable is inside `install.sh`, which hashes the
outgoing file before overwriting it and prints `Guard logic: UPDATED / unchanged /
new install`. Cite that line — visible in the orchestrator's `install.sh` output — if
you need to state whether the guard logic actually changed.

**If identical:** Log `Copy verified against source.` Then check if PROJECT_ROOT needs resolving (see below). Then proceed to Step 3.

**After copy verification (both identical and re-copied cases):** Verify PROJECT_ROOT state in the installed file:

```bash
grep '^PROJECT_ROOT = ' "<TARGET_HOOKS_DIR>/permission-guard.py"
```

- **If `INSTALL_MODE == project`:** the expected state is the unresolved placeholder `PROJECT_ROOT = "{MG_INSTALL_PROJECT_ROOT}"`. Do NOT resolve it — the runtime fallback handles it. If the value is currently an absolute path (e.g. from a prior non-project install), revert it:
  ```bash
  sed -i 's|^PROJECT_ROOT = .*|PROJECT_ROOT = "{MG_INSTALL_PROJECT_ROOT}"|' "<TARGET_HOOKS_DIR>/permission-guard.py"
  ```
  Log: `PROJECT_ROOT kept as placeholder (project mode — resolves to event.cwd at runtime)`

- **Otherwise (global/target):** if the value is empty or still the placeholder, resolve it to the absolute target path:
  ```bash
  sed -i "s|^PROJECT_ROOT = .*|PROJECT_ROOT = \"<target project>\"|" "<TARGET_HOOKS_DIR>/permission-guard.py"
  ```
  Log: `Resolved PROJECT_ROOT to <target project>`
  If already resolved to a non-empty path, no action needed.

**If different:** In the orchestrated flow this means `install.sh`'s copy did not land
(interrupted write, permissions, wrong target) — the hook was copied moments ago, so
it cannot legitimately differ. Treat it as a failed copy and re-copy. Ask via
AskUserQuestion:
- header: "Re-copy"
- question: "Installed permission-guard.py does not match source — the copy appears to have failed. Re-copy now?"
- options:
  - "Re-copy" -- "Copy the hook from source again"
  - "Continue as-is" -- "Proceed with the currently installed hook"

**If "Re-copy":**

1. Read the currently installed file to extract the resolved PROJECT_ROOT value
2. Copy the source file over:
```bash
cp "<source directory>/permission-hooks/hooks/permission-guard.py" "<TARGET_HOOKS_DIR>/permission-guard.py"
chmod +x "<TARGET_HOOKS_DIR>/permission-guard.py"
```
3. Re-resolve PROJECT_ROOT with the previously extracted value:
```bash
sed -i "s|{MG_INSTALL_PROJECT_ROOT}|<extracted-project-root>|g" "<TARGET_HOOKS_DIR>/permission-guard.py"
```

Log: `Hook re-copied from source.`

## Step 3: Settings.json Management

Check if the PreToolUse hook entries for permission-guard.py exist in the target's settings.json.

The hook needs 4 matchers: `Bash`, `Read`, `Edit`, `Write`. The same Python script handles all tool types.

In `project` mode, emit a `$CLAUDE_PROJECT_DIR`-rooted hook command (`python3 "$CLAUDE_PROJECT_DIR/.claude/permission-hooks/hooks/permission-guard.py"`). Claude Code sets `$CLAUDE_PROJECT_DIR` for hook commands regardless of the current working directory, so this form is portable across clones (ultraplan/ultrareview cloud workers included) AND survives mid-session `cd` shifts that would break a plain relative path. In `global`/`target` mode, emit an absolute path rooted at the installed `hooks_dir` (the existing behavior). Set `INSTALL_MODE` below to the value threaded through from the orchestrator.

```bash
python3 -c "
import json, os, sys

hooks_dir = '<TARGET_HOOKS_DIR>'
settings_path = '<TARGET_SETTINGS>'
install_mode = '<INSTALL_MODE>'  # 'project' | 'global' | 'target'

if install_mode == 'project':
    hook_cmd = 'python3 \"$CLAUDE_PROJECT_DIR/.claude/permission-hooks/hooks/permission-guard.py\"'
else:
    hook_cmd = 'python3 ' + os.path.join(hooks_dir, 'permission-guard.py')

# Keep the original bytes: 'stripped-then-readded' is not the same question as
# 'did the file change'. Stripping 4 stale entries and appending 4 identical ones
# is a no-op, and reporting it as a rewrite invents a restart the user does not
# need. The restart reminder keys off this comparison.
try:
    with open(settings_path) as f:
        before = f.read()
    settings = json.loads(before)
except (FileNotFoundError, json.JSONDecodeError):
    before = None
    settings = {}

hooks = settings.setdefault('hooks', {})
pre_tool = hooks.setdefault('PreToolUse', [])

matchers = ['Bash', 'Read', 'Edit', 'Write']

# Strip ALL stale permission-guard.py entries before adding fresh ones.
# A re-install (or migration from an older path scheme) could otherwise
# accumulate duplicates with mixed relative/absolute paths — exactly the
# state that masked the cwd-shift bug for so long.
stripped = 0
new_pre_tool = []
for h in pre_tool:
    if isinstance(h, dict) and h.get('matcher') in matchers:
        kept_hooks = [
            hk for hk in h.get('hooks', [])
            if not (isinstance(hk, dict)
                    and 'permission-guard.py' in hk.get('command', ''))
        ]
        stripped += len(h.get('hooks', [])) - len(kept_hooks)
        if kept_hooks:
            new_pre_tool.append({**h, 'hooks': kept_hooks})
        # else: drop the now-empty matcher entry
    else:
        new_pre_tool.append(h)

# Append fresh canonical entries.
for matcher in matchers:
    new_pre_tool.append({
        'matcher': matcher,
        'hooks': [{'type': 'command', 'command': hook_cmd}]
    })

hooks['PreToolUse'] = new_pre_tool

after = json.dumps(settings, indent=2) + '\n'

if after == before:
    print(f'UNCHANGED: 4 canonical permission-guard entries already present in {settings_path}')
else:
    with open(settings_path, 'w') as f:
        f.write(after)
    if stripped:
        print(f'REWROTE: Removed {stripped} stale permission-guard entries; added 4 fresh ones for {settings_path}')
    else:
        print(f'ADDED: Wrote 4 permission-guard hook entries to {settings_path}')
"
```

**If UNCHANGED:** The target already had the canonical entries; settings.json was not written. No restart needed.

**If ADDED:** Report that the canonical hook entries were written for the first time.

**If REWROTE:** Report that stale entries were stripped and replaced with the canonical form. This typically means the target had relative-path entries from an older install scheme that would have broken on mid-session `cd` shifts.

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
if not guard.PROJECT_ROOT or guard.PROJECT_ROOT.startswith('{'):
    print('  (unresolved placeholder -- resolves at runtime via CLAUDE_PROJECT_DIR, then event cwd)')
"
```

</process>

<completion>
## Status

After all steps complete, output a final summary:

```
Permission Guard Status
==================================================

  Target:     <target project>
  Hook file:  <TARGET_HOOKS_DIR>/permission-guard.py
  Settings:   [ADDED / REWROTE / UNCHANGED]
  Copy:       [Fresh install / Verified against source / Re-copied / Mismatch]

==================================================
```

Do not state or imply that the target "already had" the current guard logic — the copy
verification above cannot support that claim. If you need to report whether the logic
changed, quote `install.sh`'s `Guard logic:` line.

**Restart reminder — key it off Step 3's settings.json result only:**

- **If Step 3 reported ADDED or REWROTE** (the hook registration in settings.json
  changed), remind the user:
  > Note: Restart Claude Code in the target project — hook registration in settings.json is snapshotted at session start.

- **If Step 3 changed nothing**, do not ask for a restart, even when the hook file
  itself was updated. settings.json registers the hook as
  `python3 ".../permission-guard.py"`, which Claude Code spawns as a fresh subprocess
  on every PreToolUse event, so python3 re-reads the file each call and new guard logic
  is live immediately. Only the registration is session-scoped.

Then output exactly ONE of these markers as the final line:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
