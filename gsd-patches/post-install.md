# GSD Patches -- Post-Install Configuration

<objective>
Apply reusable patches to GSD workflow files in the target project. Patches are structured `.md` files containing anchor/replace pairs that customize GSD behavior. This post-install step reads patch templates directly from the source directory and applies them to the target project's GSD installation.

Each patch survives GSD updates -- after each `/gsd:update`, rerun `/mg:install` and select gsd-patches to reapply customizations.
</objective>

<context>
The target project path and source directory path are provided at the top of this prompt.
Use "the target project" and "the source directory" to reference these paths throughout.

- Target project: The project where GSD patches are being applied
- Source directory: The mg-cc-tools repository root
- Patches location: The source directory's `gsd-patches/patches/` contains all patch template files
</context>

<process>

## Step 0: Stale File Cleanup

Before applying patches, remove stale files from previous installations (v1.0 copy-based install).

Check and remove these paths in the target project if they exist:

1. `<target project>/.claude/commands/mg/apply-gsd-patches.md` -- old command file copied by v1.0 install.sh
2. `<target project>/.claude/gsd-patches/` -- old patches directory copied by v1.0 install.sh

For each path that exists, remove it and log:
```
Stale cleanup: removed <path>
```

If neither exists, log:
```
Stale cleanup: no stale files found
```

## Step 1: Resolve Target Project

The target project path is provided in the prompt prefix above. Validate that GSD is installed:

Check that `<target project>/.claude/get-shit-done/` exists. If not, report:
> POST-INSTALL: FAILED: GSD not installed at `<target project>/.claude/get-shit-done/`

## Step 2: Discover Patches

Read all `.md` files from the source directory's `gsd-patches/patches/` using Glob on `<source directory>/gsd-patches/patches/*.md`.

If no patches found, report:
> POST-INSTALL: FAILED: No patch definitions found in source directory's `gsd-patches/patches/`

List discovered patches:
```
Found N patch(es):
  - patch-name.md -- [description from Meta section]
```

## Step 3: Pre-flight Patch Review

Before applying anything, review each patch against the current GSD version to detect upstream changes in the patched areas.

**For each patch:**

1. Read the patch file from the source directory and parse each modification's **Anchor** text.
2. Read the target file from `<target project>/.claude/<target-path>`.
3. For each modification, check whether the **Anchor** text exists verbatim in the target file.

**If all anchors match across all patches:**
```
Pre-flight check: All patches compatible with current GSD version.
```
Proceed directly to Step 4 (Apply Each Patch).

**If any anchor does NOT match:**

For each mismatched modification:

1. Use Grep to locate the general area in the target file (search for a distinctive fragment from the anchor -- e.g., the first meaningful line).
2. Read the surrounding context (+/- 15 lines) from the target file.
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

Analysis: [Brief explanation of what changed]

The patch [is still useful / may need adjustment / is no longer needed] because:
  [reasoning]
```

5. Ask the user via AskUserQuestion:
   - header: "Patch drift"
   - question: "Modification N of [patch-name] has anchor drift. How should I proceed?"
   - options:
     - "Update patch" -- "Update the patch definition in mg-cc-tools to match the new GSD version"
     - "Still apply as-is" -- "Proceed to apply step; handle the mismatch via conflict resolution"
     - "Skip this patch" -- "Don't apply this patch at all"

6. **If "Update patch":** Edit the patch `.md` file in the source directory's `gsd-patches/patches/` to update the **Anchor** (and **Replace with** if needed) so they align with the current GSD version. Track that a patch file was modified.

7. **If "Still apply as-is":** Mark this patch for normal conflict resolution in Step 4.

8. **If "Skip this patch":** Exclude this patch from Step 4.

**After reviewing all patches, if any patch files were modified:**

```
--- Patch definitions updated ---

Modified patches:
  - [patch-name].md -- Modification N anchor updated

Updated in source: <source directory>/gsd-patches/patches/
```

Proceed to Step 4 with the updated patches.

**If no patch files were modified:** Proceed to Step 4.

## Step 4: Apply Each Patch

For each patch file, parse its structure and apply modifications.

### 4a. Parse Patch File

Read the patch `.md` file from the source directory's `gsd-patches/patches/`. Extract from the `## Meta` section:
- **Target:** -- relative path within `.claude/` (e.g., `get-shit-done/workflows/discuss-phase.md`)
- **Description:** -- human-readable description

Extract each `### N. ...` subsection under `## Modifications`. Each modification has:
- **Anchor:** -- the exact text block to find in the target file (in a fenced code block)
- **Replace with:** -- the replacement text (in a fenced code block)

### 4b. Read Target File

Read `<target project>/.claude/<target-path>`. If the file doesn't exist, report and skip this patch:
> "Target file not found: `<target-path>`. Skipping patch."

### 4c. Apply Each Modification

For each modification in the patch:

1. **Idempotency check:** Search for the **Replace with** text in the target file. If it already exists, skip with message:
   > "Modification N already applied -- skipping."

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
       - "Adapt patch" -- "I'll analyze the new structure and apply the intended change"
       - "Skip this modification" -- "Leave this modification unapplied"
       - "Abort this patch" -- "Stop applying this patch (remaining modifications skipped)"
       - "Abort all" -- "Stop all patch application"
   - **Adapt patch:** Read the surrounding context, understand the structural change, and apply the intended behavioral change to the new structure using Edit. Report what was adapted.
   - **Skip:** Move to next modification.
   - **Abort this patch:** Move to next patch.
   - **Abort all:** Stop entirely and go to summary.

### 4d. Report Patch Result

After all modifications for a patch:
```
Patch [patch-name]: N/M modifications applied
  1. [description] -- applied / already applied / skipped / adapted / conflict
  2. [description] -- applied / already applied / skipped / adapted / conflict
```

## Step 5: Summary

After all patches are processed:

```
--- GSD Patches Summary ---

Target: <target project>
Patches: N processed

  [patch-name]:
    Modification 1: [status]
    Modification 2: [status]

  [patch-name]:
    ...

---
```

If all modifications were "already applied", add:
> "All patches already applied -- target is up to date."

</process>

<important_notes>
- **Only modify mg-cc-tools patch files during Step 3 (Pre-flight Patch Review)** when the user explicitly chooses "Update patch". All other modifications go to the target project only.
- **Preserve exact whitespace** in anchors and replacements -- the Edit tool requires exact matches.
- **Read before editing** -- always Read the target file before attempting Edit operations.
- When parsing patch files, the anchor and replacement text are inside fenced code blocks (triple backticks). Extract the content between the fences, not including the fence markers themselves.
</important_notes>

<completion>
## Status

After all steps complete, output exactly ONE of these markers as the final line:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
