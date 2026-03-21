# Phase 1: Rename to Auto-Doc + Pipeline Cleanup

**Goal:** Rename the tool family from `create-docs` to `auto-doc` and clean up dead code, orphaned agents, and latent bugs discovered during the v1.0 analysis. This clears the deck for all subsequent v1.1 work.

**Depends on:** Nothing (first phase)

---

## Part A: Rename create-docs → auto-doc

### Rationale

The tool family is growing beyond "create docs":
- `/mg:create-docs` — full pipeline router
- `/mg:create-docs-scan` — scan step
- `/mg:create-docs-generate` — generate step
- `/mg:create-docs-verify` — verify step
- `/mg:add-docs` — add notes
- `/mg:auto-doc-script` — new script README generator (Phase 2)

"auto-doc" better describes the automated documentation lifecycle and is shorter. The new script command would be awkward as `/mg:create-docs-script`.

### Rename Map

#### Commands (slash commands)

| Current | New |
|---------|-----|
| `/mg:create-docs` | `/mg:auto-doc` |
| `/mg:create-docs-scan` | `/mg:auto-doc-scan` |
| `/mg:create-docs-generate` | `/mg:auto-doc-generate` |
| `/mg:create-docs-verify` | `/mg:auto-doc-verify` |
| `/mg:add-docs` | `/mg:auto-doc-add` or `/mg:add-docs` (keep?) |

#### Directory structure

| Current | New |
|---------|-----|
| `create-docs/` | `auto-doc/` |
| `create-docs/commands/create-docs.md` | `auto-doc/commands/auto-doc.md` |
| `create-docs/commands/create-docs-scan.md` | `auto-doc/commands/auto-doc-scan.md` |
| `create-docs/commands/create-docs-generate.md` | `auto-doc/commands/auto-doc-generate.md` |
| `create-docs/commands/create-docs-verify.md` | `auto-doc/commands/auto-doc-verify.md` |
| `create-docs/commands/add-docs.md` | `auto-doc/commands/auto-doc-add.md` (or keep name) |
| `create-docs/agents/` | `auto-doc/agents/` |
| `create-docs/scripts/` | `auto-doc/scripts/` |
| `create-docs/references/` | `auto-doc/references/` |
| `create-docs/install.sh` | `auto-doc/install.sh` |

#### Target project paths

| Current | New |
|---------|-----|
| `.claude/commands/mg/create-docs.md` | `.claude/commands/mg/auto-doc.md` |
| `.claude/create-docs/` | `.claude/auto-doc/` |
| `.mg/docs/` | `.mg/docs/` (unchanged — project data, not tool namespace) |

#### Internal references

All cross-references between commands, agents, and scripts use `{SCRIPTS_DIR}`, `{TEMPLATES_DIR}`, etc. — sed-resolved at install time. These stay the same. References that need updating:
- Command files referencing other commands by name (e.g., "Run `/mg:create-docs-generate`")
- Agent files referencing command names in their instructions
- Schema and style guide if they mention command names
- CLAUDE.md in this repo
- `.planning/` files (historical — don't rename, just update ROADMAP going forward)

### Execution Strategy

Clean rename (Option A). Rename the directory and all files in one pass. Update all internal references. Breaking change — users reinstall via `/mg:install`.

Migration path:
1. `/mg:install` detects old `create-docs` installation
2. Removes old `.claude/commands/mg/create-docs*.md` and `.claude/create-docs/`
3. Deploys new `auto-doc` structure

---

## Part B: Pipeline Cleanup

Dead code and bugs discovered during the v1.0 analysis session. Fix these while renaming since we're touching every file anyway.

### 1. Delete orphaned `staleness-scanner.md`

**File:** `agents/staleness-scanner.md`

Created in Phase 2, never wired into any command. The scan pipeline calls `staleness-check.py` directly instead of delegating to this agent. The agent references `--doc-file` parameters that don't exist in either script (both only support `--docs-dir`), and its output format doesn't match what `staleness-check.py` actually produces.

**Action:** Delete the file. `install.sh` uses wildcard copy (`agents/*.md`), so no install script change needed.

### 2. Remove dead `check-references.py` call from scan pipeline

**File:** `commands/auto-doc-scan.md` (was `create-docs-scan.md`, Step 3: Staleness Check, lines 173-179; also line 290)

The scan command runs `check-references.py --docs-dir` and writes to `refs-check.json`. But `merge-scan.py` skips this file — `merge-scan.py` line 166 checks `isinstance(data, dict)` and the output is a flat JSON array, so it hits the `"not a JSON object"` warning path and is silently discarded. The file sits in scan-logs unread.

Reference checking is a verify concern (correctness), not a scan concern (staleness). `staleness-check.py` handles what scan needs.

**Action:** Remove the `check-references.py` invocation from Step 3 and the mention at line 290. Keep the `staleness-check.py` call.

### 3. Retire `check-references.py`

The scan pipeline call (item 2) is the only remaining invocation — once removed, the script has no consumers. The verify pipeline's split-output optimization (`--output-broken`, `--output-symbols`) was a stepping stone; the reference manifest (Phase 3) replaces extraction entirely.

**Action:** Delete `check-references.py`, `tests/test_check_references.py`, and all references to `verify-refs-broken.json`/`verify-refs-symbols.json` in `auto-doc-verify.md` and `verifier.md`. Remove the `--clean` entries for these files from `list-verify-findings.py`.

### 4. Fix `note_id` vs `id` field mismatch

**Files:**
- `scripts/add-note.py` line 78: writes `"id": note_id`
- `scripts/classify-note.py` line 153: reads `note["id"]`
- `references/schema.md`: documents the field as `"note_id"`
- `commands/auto-doc-add.md`: references `note_id`
- `commands/auto-doc-generate.md`: reads `note_id`

`add-note.py` writes `"id"` but every consumer expects `"note_id"`. `classify-note.py` has the same mismatch. Latent bug — would surface the first time notes are used in generate update mode.

**Action:** Change `add-note.py` to write `"note_id"`. Fix `classify-note.py` to read `note["note_id"]`. Update `test_add_note.py` and `test_classify_note.py` assertions.

---

## Scope Summary

| Action | Files |
|--------|-------|
| Rename/move | ~53 files (entire `create-docs/` tree) |
| Delete | 3 files (staleness-scanner.md, check-references.py, test_check_references.py) |
| Edit (cross-references) | ~12 files (commands, agents, schema, CLAUDE.md, install.sh) |
| Edit (bug fix) | 4 files (add-note.py, classify-note.py + their tests) |
| New | 0 files |
