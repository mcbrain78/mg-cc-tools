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
Source patches directory: {SOURCE_PATCHES_DIR}
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

## Step 3: Pre-flight Patch Review

Before applying anything, review each patch against the current GSD version to detect upstream changes in the patched areas.

**For each patch:**

1. Read the patch file and parse each modification's **Anchor** text.
2. Read the target file from `<TARGET_PROJECT>/.claude/<target-path>`.
3. For each modification, check whether the **Anchor** text exists verbatim in the target file.

**If all anchors match across all patches:**
```
Pre-flight check: All patches compatible with current GSD version.
```
Proceed directly to Step 4 (Apply Each Patch).

**If any anchor does NOT match:**

For each mismatched modification:

1. Use Grep to locate the general area in the target file (search for a distinctive fragment from the anchor — e.g., the first meaningful line).
2. Read the surrounding context (±15 lines) from the target file.
3. Compare with the patch's anchor and replacement to understand what changed upstream.
4. Present the analysis to the user:

```
Patch: [patch-name]
Modification N: [description]

The GSD version has changed in this area.

Anchor expects:
  [first 3-5 lines of anchor text...]

Current GSD has:
  [corresponding lines from target file...]

Analysis: [Brief explanation of what changed — e.g., "GSD added a recommendation
suffix to the options line" or "The step was restructured with new sub-bullets"]

The patch [is still useful / may need adjustment / is no longer needed] because:
  [reasoning]
```

5. Ask the user via AskUserQuestion:
   - header: "Patch drift"
   - question: "Modification N of [patch-name] has anchor drift. How should I proceed?"
   - options:
     - "Update patch" — "Update the patch definition in mg-cc-tools to match the new GSD version"
     - "Still apply as-is" — "Proceed to apply step; handle the mismatch via conflict resolution"
     - "Skip this patch" — "Don't apply this patch at all"

6. **If "Update patch":** Edit the patch `.md` file in the patches directory to update the **Anchor** (and **Replace with** if needed) so they align with the current GSD version. Track that a patch file was modified.

7. **If "Still apply as-is":** Mark this patch for normal conflict resolution in Step 4.

8. **If "Skip this patch":** Exclude this patch from Step 4.

**After reviewing all patches, if any patch files were modified:**

Sync modified patches back to the source directory so the repo stays in sync:

```bash
cp "{PATCHES_DIR}/<modified-patch>.md" "{SOURCE_PATCHES_DIR}/<modified-patch>.md"
```

Repeat for each modified patch file.

```
--- Patch definitions updated ---

Modified patches:
  - [patch-name].md — Modification N anchor updated

Synced to source: {SOURCE_PATCHES_DIR}/

The updated patch definitions need to be reloaded.
Please exit Claude (/exit) and restart, then re-run:

  /mg:apply-gsd-patches [same-target-argument]
```

**Stop here — do not proceed to Step 4.** The command file is loaded at conversation start, so changes to patch definitions won't take effect until the next session.

**If no patch files were modified:** Proceed to Step 4.

## Step 4: Apply Each Patch

For each patch file, parse its structure and apply modifications.

### 4a. Parse Patch File

Read the patch `.md` file. Extract from the `## Meta` section:
- **Target:** — relative path within `.claude/` (e.g., `get-shit-done/workflows/discuss-phase.md`)
- **Description:** — human-readable description

Extract each `### N. ...` subsection under `## Modifications`. Each modification has:
- **Anchor:** — the exact text block to find in the target file (in a fenced code block)
- **Replace with:** — the replacement text (in a fenced code block)

### 4b. Read Target File

Read `<TARGET_PROJECT>/.claude/<target-path>`. If the file doesn't exist, report and skip this patch:
> "Target file not found: `<target-path>`. Skipping patch."

### 4c. Apply Each Modification

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

### 4d. Report Patch Result

After all modifications for a patch:
```
Patch [patch-name]: N/M modifications applied
  1. [description] — applied / already applied / skipped / adapted / conflict
  2. [description] — applied / already applied / skipped / adapted / conflict
```

## Step 5: Summary

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
- **Only modify mg-cc-tools patch files during Step 3 (Pre-flight Patch Review)** when the user explicitly chooses "Update patch". All other modifications go to the target project only.
- **Always sync modified patches back to source** — after editing any patch file in `{PATCHES_DIR}`, copy it to `{SOURCE_PATCHES_DIR}` so the repo stays in sync.
- **Preserve exact whitespace** in anchors and replacements — the Edit tool requires exact matches.
- **Read before editing** — always Read the target file before attempting Edit operations.
- When parsing patch files, the anchor and replacement text are inside fenced code blocks (triple backticks). Extract the content between the fences, not including the fence markers themselves.
</important_notes>
