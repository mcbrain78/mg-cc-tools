# [Tool Name] -- Post-Install Configuration

<objective>
[What this post-install step does and why it cannot be done by install.sh alone.
Post-install steps require Claude Code intelligence for tasks like JSON merging,
interactive configuration, conflict resolution, or conditional patching that
cannot be handled by simple file copies.]
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

<completion>
## Status

After all steps complete, output exactly ONE of these markers as the final line:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
