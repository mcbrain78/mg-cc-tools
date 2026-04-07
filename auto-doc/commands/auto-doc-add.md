---
name: mg:auto-doc-add
description: Capture a documentation note to inbox with auto-classification
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Add Documentation Note

You capture documentation notes to the inbox for later processing by the generate pipeline. This is a **standalone command** -- it does not trigger any pipeline step (scan, generate, or verify). Notes stay in the inbox until `/mg:auto-doc-generate` processes them.

## Session Context

Run the session context emitter for permission auto-approval:
```
python3 {MG_INSTALL_EMIT_CONTEXT_SCRIPT} AUTO-DOC
```
If the script is not found, continue — permissions will require manual approval.

## Arguments

`$ARGUMENTS` contains the note text. Example usage:

```
/mg:auto-doc-add "Document the new auth flow for JWT tokens"
```

## Process

### Step 1: Parse and Validate

1. **Extract note text from `$ARGUMENTS`.** If empty or missing, tell the user:
   ```
   Usage: /mg:auto-doc-add "your note text here"
   ```
   Then stop.

2. **Check `.mg/docs/` directory exists.** If not, tell the user:
   ```
   Error: Documentation workspace not found. Run /mg:auto-doc first to initialize.
   ```
   Then stop.

3. **Check `.mg/docs/notes-inbox.json` exists.** If not, create it with the initial structure:
   ```json
   {"notes": []}
   ```
   Write this to `<project_root>/.mg/docs/notes-inbox.json`.

### Step 2: Detect Context

Gather contextual information to improve note classification and traceability.

1. **Active file context.** Check if the user has an active file open (use whatever context is available to you as an LLM). If you can determine the active file path, store it as `file_arg`. If unclear or unavailable, set `file_arg` to an empty string.

2. **GSD phase context.** Check if `.planning/STATE.md` exists in the project root:
   - If it exists, read it and extract the current phase name from the "Current focus:" line or the "Phase:" line.
   - Store the extracted phase name as `phase_arg`.
   - If `.planning/STATE.md` does not exist, set `phase_arg` to an empty string.

3. **Identify project root.** Determine the project root directory by looking for common root indicators (`.git`, `package.json`, `pyproject.toml`). Store as `project_root`.

### Step 3: Add Note to Inbox

Run `add-note.py` to append the note to the inbox:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/add-note.py \
  --inbox <project_root>/.mg/docs/notes-inbox.json \
  --text "<user_note_text>" \
  --phase "<phase_arg>" \
  --file "<file_arg>"
```

Capture stdout -- it returns JSON with the new `note_id`.

Extract the `note_id` from the JSON output (e.g., `NOTE-001`).

### Step 4: Classify the Note

Run `classify-note.py` to auto-classify the note by audience, document, and section:

```bash
uv run {MG_INSTALL_SCRIPTS_DIR}/classify-note.py \
  --text "<user_note_text>" \
  --note-id <note_id_from_step_3> \
  --inbox <project_root>/.mg/docs/notes-inbox.json
```

The script outputs classification JSON to stdout AND updates the note in the inbox file.

Parse the classification from stdout: `audience`, `document`, `section`, `confidence`.

### Step 5: Present and Offer Correction

Display the classification result to the user:

```
Note added: {note_id}
Classification:
  Audience:   {audience}
  Document:   {document}
  Section:    {section}
  Confidence: {confidence:.0%}
```

Then use AskUserQuestion to let the user accept or correct the classification:

- **header:** "Classification"
- **question:** "Accept this classification? If not, provide corrections."
- **options:**
  - "Accept" -- "Classification looks correct"
  - "Correct" -- "I'll specify the correct audience, document, or section"

**If "Accept":** Done. Print:
```
Note saved. It will be used by /mg:auto-doc-update and /mg:auto-doc-generate.
```

**If "Correct":** Ask the user for the correct values via a follow-up AskUserQuestion with these fields:
- Audience (e.g., developers, end-users, agents, devops)
- Document (e.g., ARCHITECTURE, USER_GUIDE, SYSTEM_MAP)
- Section (e.g., auth-flow, getting-started)

Then update the note in the inbox:
1. Read `<project_root>/.mg/docs/notes-inbox.json`
2. Find the note with the matching `note_id`
3. Update the `audience`, `document`, and/or `section` fields with the user's corrections
4. Write the complete updated inbox back to the same file

Print:
```
Classification updated. Note saved. It will be used by /mg:auto-doc-update and /mg:auto-doc-generate.
```

## Important Principles

- **Standalone command.** This command never triggers scan, generate, or verify. It only writes to the notes inbox.
- **One note at a time.** No batch ingestion for v1. Users can run `/mg:auto-doc-add` multiple times for multiple notes.
- **GSD phase context detection is best-effort.** If `.planning/` does not exist, skip phase detection. Do not error on missing GSD state.
- **Active file context is best-effort.** Pass an empty string if the active file cannot be determined.
- **The note stays in inbox until `/mg:auto-doc-generate` processes it.** This command does not integrate notes into documentation.
- **Use `{MG_INSTALL_SCRIPTS_DIR}` placeholder for script paths** -- resolved by install.sh at install time.
- **Do not modify `add-note.py` or `classify-note.py`.** Use them as-is through their CLI interface.
- **Do not modify `install.sh`.** The auto-doc-add command is already in the COMMANDS array.
