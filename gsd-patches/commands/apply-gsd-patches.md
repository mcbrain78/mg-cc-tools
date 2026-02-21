# Apply GSD Patches

---
name: mg:apply-gsd-patches
description: Apply GSD workflow patches to a target project
argument-hint: "<project-name-or-path>"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - AskUserQuestion
  - Bash
---

<objective>
Apply reusable patches to GSD workflow files in a target project. Patches survive GSD updates — after each `/gsd:update`, rerun this command to reapply customizations.

Each patch is a `.md` file in `{PATCHES_DIR}` containing structured anchor/replace pairs. The command discovers all patches automatically, checks for idempotency, and handles conflicts gracefully.
</objective>

<context>
Target project argument: $ARGUMENTS

Patches directory: {PATCHES_DIR}
</context>

<process>

## Step 1: Resolve Target Project

The argument `$ARGUMENTS` is either:
- A **project name** (e.g., `ai-stock-ranker`) — resolve as a sibling directory of mg-cc-tools. The working directory is inside mg-cc-tools, so the sibling is at `../../<name>` relative to cwd, or more reliably: determine the parent of mg-cc-tools and append the project name.
- An **absolute path** (starts with `/`) — use directly.

**Resolution logic:**
1. If `$ARGUMENTS` starts with `/`, use it as-is → `TARGET_PROJECT=$ARGUMENTS`
2. Otherwise, resolve as sibling: find mg-cc-tools root (look for this repo's `.git`), go up one level, append the project name → `TARGET_PROJECT=<parent>/<name>`

**Validate:** Check that `<TARGET_PROJECT>/.claude/get-shit-done/` exists. If not, report the error and stop:
> "Could not find GSD installation at `<TARGET_PROJECT>/.claude/get-shit-done/`. Is GSD installed in that project?"

If `$ARGUMENTS` is empty, ask the user:
> "Which project should I apply GSD patches to? Provide a project name (sibling directory) or absolute path."

## Step 2: Discover Patches

Read all `.md` files from the patches directory using Glob on `{PATCHES_DIR}/*.md`.

If no patches found, report and stop:
> "No patch definitions found in `{PATCHES_DIR}/`."

List discovered patches:
```
Found N patch(es):
  - patch-name.md — [description from Meta section]
```

## Step 3: Apply Each Patch

For each patch file, parse its structure and apply modifications.

### 3a. Parse Patch File

Read the patch `.md` file. Extract from the `## Meta` section:
- **Target:** — relative path within `.claude/` (e.g., `get-shit-done/workflows/discuss-phase.md`)
- **Description:** — human-readable description

Extract each `### N. ...` subsection under `## Modifications`. Each modification has:
- **Anchor:** — the exact text block to find in the target file (in a fenced code block)
- **Replace with:** — the replacement text (in a fenced code block)

### 3b. Read Target File

Read `<TARGET_PROJECT>/.claude/<target-path>`. If the file doesn't exist, report and skip this patch:
> "Target file not found: `<target-path>`. Skipping patch."

### 3c. Apply Each Modification

For each modification in the patch:

1. **Idempotency check:** Search for the **Replace with** text in the target file. If it already exists → skip with message:
   > "Modification N already applied — skipping."

2. **Anchor match:** Search for the **Anchor** text verbatim in the target file.

3. **If anchor found:** Apply the replacement using the Edit tool:
   - `old_string` = the anchor text
   - `new_string` = the replacement text
   - Report: "Modification N applied successfully."

4. **If anchor NOT found:** Conflict resolution:
   - Use Grep to find a distinctive fragment from the anchor (first meaningful line) in the target file
   - Show the user the nearby context from the target file
   - Present options via AskUserQuestion:
     - header: "Conflict"
     - question: "Anchor text not found for modification N of [patch-name]. The target file may have changed. How should I proceed?"
     - options:
       - "Adapt patch" — "I'll analyze the new structure and apply the intended change"
       - "Skip this modification" — "Leave this modification unapplied"
       - "Abort this patch" — "Stop applying this patch (remaining modifications skipped)"
       - "Abort all" — "Stop all patch application"
   - **Adapt patch:** Read the surrounding context, understand the structural change, and apply the intended behavioral change to the new structure using Edit. Report what was adapted.
   - **Skip:** Move to next modification.
   - **Abort this patch:** Move to next patch.
   - **Abort all:** Stop entirely and go to summary.

### 3d. Report Patch Result

After all modifications for a patch:
```
Patch [patch-name]: N/M modifications applied
  1. [description] — applied / already applied / skipped / adapted / conflict
  2. [description] — applied / already applied / skipped / adapted / conflict
```

## Step 4: Summary

After all patches are processed:

```
--- GSD Patches Summary ---

Target: <TARGET_PROJECT>
Patches: N processed

  [patch-name]:
    Modification 1: [status]
    Modification 2: [status]

  [patch-name]:
    ...

---
```

If all modifications were "already applied", add:
> "All patches already applied — target is up to date."

</process>

<important_notes>
- **Never modify files in mg-cc-tools.** Only modify files in the target project.
- **Preserve exact whitespace** in anchors and replacements — the Edit tool requires exact matches.
- **Read before editing** — always Read the target file before attempting Edit operations.
- When parsing patch files, the anchor and replacement text are inside fenced code blocks (triple backticks). Extract the content between the fences, not including the fence markers themselves.
</important_notes>
