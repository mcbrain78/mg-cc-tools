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
python3 "<source directory>/install/scripts/merge-hook-entry.py" \
  --settings "<TARGET_SETTINGS>" \
  --install-mode "<INSTALL_MODE>" \
  --hook-rel-path ".claude/transcript/hooks/inject-transcript-path.py" \
  --hook-abs-path "<TARGET_HOOK>" \
  --matcher Bash
```

**If ADDED:** Report that the hook was registered for the first time.

**If REWROTE:** Report that stale entries were stripped and replaced with the canonical
form. This is expected on a target installed under an older scheme, which wrote a plain
relative command path (broken by any mid-session `cd`) and whose registration check could
never match it — so every re-install appended another duplicate entry. The rewrite
collapses those duplicates into one canonical entry.

**If UNCHANGED:** The canonical entry was already present; settings.json was not written.

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
