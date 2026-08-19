# [Tool Name] -- Post-Install Configuration

<objective>
[What this post-install step does and why it cannot be done by install.sh alone.
Post-install steps require Claude Code intelligence for tasks like interactive
configuration, conflict resolution, or conditional patching that cannot be
handled by simple file copies.]

Registering a hook in settings.json is NOT one of those tasks -- call
`install/scripts/merge-hook-entry.py` instead of writing a merge here. It
canonicalises entries (so re-running is idempotent), emits the portable
`$CLAUDE_PROJECT_DIR`-rooted command form in project mode, and reports
ADDED / REWROTE / UNCHANGED. Four tools each hand-rolled this merge in
embedded Python and all four drifted: two wrote relative command paths that
break on a mid-session `cd`, two could never match their own entries and
appended a duplicate on every run, and one reported a rewrite when the file
had not changed. Per CLAUDE.md, deterministic logic belongs in scripts/*.py,
not in a markdown fence where nothing can test it.
</objective>

<context>
The target project path and source directory path are provided at the top of this prompt.
Use "the target project" and "the source directory" to reference these paths throughout.

- Target project: The project where the tool is being installed
- Source directory: The mg-cc-tools repository root
</context>

<process>
## Step 1: [First step]

[Instructions for the first step. Reference paths using natural language:
"Read the file at the source directory's `<tool-name>/path/to/resource`"
"Write to the target project's `.claude/path/to/destination`"]

## Step N: [Last step]

[Instructions for the final step.]
</process>

<reporting>
## Report only what your evidence proves

Every conclusion this step reports to the user must be traceable to something it
actually checked. Three failure modes have been found in shipped post-install
steps, all of which read as thorough while being false:

1. **A check that runs after the state it measures was already written.**
   `install.sh` runs BEFORE this file, so anything it copied is already in place.
   Comparing a just-copied file against its source proves the copy landed -- it
   cannot tell you what the target held beforehand, and must never be reported as
   "already current", "in sync", or "nothing changed". If you need to know whether
   content actually changed, the only place that is observable is inside
   `install.sh`, before it overwrites.

2. **A change announced without a comparison.** "Wrote N entries" is not a
   finding unless you compared before to after. A no-op and a real edit look
   identical otherwise. Scripts called from here should report an explicit
   unchanged result, and you should pass it through rather than flatten it into
   a generic success.

3. **Advice derived from the wrong signal.** Restart advice is the recurring
   example: a hook script's *content* is live on the next tool call, because
   Claude Code spawns the command as a fresh subprocess per event. What is
   snapshotted at session start is the *registration* in settings.json. So ask
   for a restart when registration changed, never merely because a script file
   was updated.

When a step cannot substantiate a conclusion, say what was verified and stop
there. An honest narrower report is worth more than a confident wrong one.
</reporting>

<completion>
## Status

After all steps complete, output exactly ONE of these markers as the final line:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
