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
python3 "<source directory>/install/scripts/merge-hook-entry.py" \
  --settings "<target project>/.claude/settings.json" \
  --install-mode "<INSTALL_MODE>" \
  --hook-rel-path ".claude/cc-regression-test/hooks/intercept-trigger.py" \
  --hook-abs-path "<target project>/.claude/cc-regression-test/hooks/intercept-trigger.py" \
  --matcher Bash
```

The script handles all three settings.json states listed above (missing file, no `hooks` key,
no `PreToolUse` array), backs up and replaces the file only if it is unparseable JSON, and
reports one of:

**ADDED** — the entry was written for the first time.

**REWROTE** — stale entries referencing `intercept-trigger.py` were stripped and replaced.
Expected on a target installed under the older scheme: install time wrote a plain relative
command path while the runtime command wrote an absolute one, so neither could recognise the
other and duplicates accumulated. The rewrite collapses them into one canonical entry.

**UNCHANGED** — the canonical entry was already present; the file was not written.

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
