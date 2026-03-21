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
| `/mg:add-docs` | `/mg:auto-doc-add` |

#### Directory structure

| Current | New |
|---------|-----|
| `create-docs/` | `auto-doc/` |
| `create-docs/commands/create-docs.md` | `auto-doc/commands/auto-doc.md` |
| `create-docs/commands/create-docs-scan.md` | `auto-doc/commands/auto-doc-scan.md` |
| `create-docs/commands/create-docs-generate.md` | `auto-doc/commands/auto-doc-generate.md` |
| `create-docs/commands/create-docs-verify.md` | `auto-doc/commands/auto-doc-verify.md` |
| `create-docs/commands/add-docs.md` | `auto-doc/commands/auto-doc-add.md` |
| `create-docs/agents/` | `auto-doc/agents/` |
| `create-docs/scripts/` | `auto-doc/scripts/` |
| `create-docs/references/` | `auto-doc/references/` |
| `create-docs/install.sh` | `auto-doc/install.sh` |
| `create-docs/tool.toml` | `auto-doc/tool.toml` |

#### Target project paths

| Current | New |
|---------|-----|
| `.claude/commands/mg/create-docs.md` | `.claude/commands/mg/auto-doc.md` |
| `.claude/create-docs/` | `.claude/auto-doc/` |
| `.mg/docs/` | `.mg/docs/` (unchanged — project data, not tool namespace) |

#### Install infrastructure

| File | Changes needed |
|------|---------------|
| `auto-doc/install.sh` | Rename `SUPPORT_DIR` from `create-docs` to `auto-doc` (line 172), update `COMMANDS` array entries, update all echo statements, add old-installation cleanup (see migration path) |
| `install/scripts/mg-install-lib.py` | Rename workspace mapping `"create-docs": ".mg/docs"` → `"auto-doc": ".mg/docs"` (line 62) |

#### Internal references

All cross-references between commands, agents, and scripts use `{SCRIPTS_DIR}`, `{TEMPLATES_DIR}`, etc. — sed-resolved at install time. These stay the same. References that need updating:
- Command files referencing other commands by name (e.g., "Run `/mg:create-docs-generate`")
- Agent files referencing command names in their instructions
- Schema and style guide if they mention command names
- CLAUDE.md in this repo
- `.planning/` files (historical — don't rename, just update ROADMAP going forward)

**Non-trivial rename:** `add-docs` → `auto-doc-add` is the only command that does not follow a simple `s/create-docs/auto-doc/g` pattern. The verb moves from prefix to suffix (`add-docs` → `auto-doc-add`). A naive sed replacement will not catch it — this rename must be handled explicitly in addition to the bulk substitution.

**Verification:** After rename, grep the entire `auto-doc/` tree for any remaining `create-docs` or `add-docs` references. Any hits are bugs.

### Execution Strategy

Clean rename (Option A). Rename the directory and all files in one pass. Update all internal references. Breaking change — users reinstall via `/mg:install`.

Migration path (logic to build in `auto-doc/install.sh`):
1. Before deploying, check for old installation: test if `.claude/commands/mg/create-docs.md` or `.claude/create-docs/` exists
2. If found, remove `.claude/commands/mg/create-docs*.md` and `rm -rf .claude/create-docs/`
3. Remove the stale `create-docs` entry from the manifest JSON (the manifest is at `<target>/.claude/mg-tools-manifest.json` — read it, delete the `create-docs` key if present, write it back). `mg-install-lib.py update-manifest` only adds entries; it does not remove old ones.
4. Deploy new `auto-doc` structure as normal
5. Run `mg-install-lib.py update-manifest --tool auto-doc --source <source_dir> --target <target_dir>` to register the new tool

---

## Part B: Pipeline Cleanup

Dead code and bugs discovered during the v1.0 analysis session. Fix these while renaming since we're touching every file anyway.

### 1. Delete orphaned `staleness-scanner.md`

**File:** `agents/staleness-scanner.md`

Created in Phase 2, never wired into any command. The scan pipeline calls `staleness-check.py` directly instead of delegating to this agent. The agent references `--doc-file` parameters that don't exist in either script (both only support `--docs-dir`), and its output format doesn't match what `staleness-check.py` actually produces.

**Action:** Delete the file. `install.sh` uses wildcard copy (`agents/*.md`), so no install script change needed.

### 2. Remove dead `check-references.py` call from scan pipeline

**File:** `commands/auto-doc-scan.md` (was `create-docs-scan.md`, Step 3: Staleness Check, lines 173-179; also line 290)

The scan command runs `check-references.py --docs-dir` and writes to `refs-check.json`. This file is discarded by `merge-scan.py` for two reasons: (1) the output is a flat JSON array that fails the `isinstance(data, dict)` check at line 166, and more importantly, (2) `merge-scan.py` has no consumer key for reference data — it only merges `source_material_index`, `staleness_report`, `note_classifications`, `gap_analysis`, `project_model`, and `gsd_context`. Even if the format were fixed, the data would have nowhere to go.

Reference checking is a verify concern (correctness), not a scan concern (staleness).

**Action:** Remove the `check-references.py` invocation from Step 3 and the mention at line 290.

### 3. Fix `staleness-check.py` output format for merge

**File:** `scripts/staleness-check.py` (line 275)

`staleness-check.py` writes its output as a flat JSON array via `save_json(args.output, entries)`. But `merge-scan.py` line 166 checks `isinstance(data, dict)` and skips non-dict files — the same bug as `check-references.py` (item 2). This means staleness data has never been merged into `docs-scan.json`. The scan pipeline runs the script, writes to `scan-logs/staleness-results.json`, and `merge-scan.py` silently discards it.

`merge-scan.py` line 179 expects a `staleness_report` key inside a dict. The output format must match.

**Action:** Wrap `staleness-check.py` CLI output in a dict: `save_json(args.output, {"staleness_report": entries})` at line 275. The `check_staleness()` function itself continues to return a bare list (internal API). Only CLI-level tests need updating: `TestCLI.test_cli_json_output` (line 334) and `TestCLI.test_cli_output_file` (line 353) should assert `isinstance(data, dict)` with a `staleness_report` key. Function-level tests (`TestStalenessDetection`, `TestSeverity`, `TestOutputFormat`) remain unchanged.

### 4. Keep `check-references.py` for verify pipeline

After removing the scan invocation (item 2), `check-references.py` has no scan consumers. The verify pipeline still depends on it: `auto-doc-verify.md` Step 2 runs `check-references.py --skip-symbol-check --output-broken --output-symbols` and feeds the output to the verifier agent. Phase 3 will retire the script when the reference manifest replaces it. No changes needed in Phase 1.

### 5. Fix `note_id` vs `id` field mismatch

**The actual mismatch:** The Python scripts (`add-note.py`, `classify-note.py`) are internally consistent — both use the field name `"id"`. The schema (`references/schema.md`) and command files (`auto-doc-add.md`, `auto-doc-generate.md`) are also internally consistent — both use `"note_id"`. The mismatch is between the code layer and the documentation/schema layer.

**Files using `"id"` (code):**
- `scripts/add-note.py` line 78: writes `"id": note_id`
- `scripts/add-note.py` line 37: `next_note_id()` reads `note.get("id", "")`
- `scripts/classify-note.py` line 153: reads `note["id"]`

**Files using `"note_id"` (schema/commands):**
- `references/schema.md`: documents the field as `"note_id"`
- `commands/auto-doc-add.md`: references `note_id`
- `commands/auto-doc-generate.md`: reads `note_id`

**Why `"note_id"` wins:** The schema is the shared contract between pipeline steps. Generate reads `note_id` from `docs-scan.json` — this is the integration boundary. Aligning the scripts to the schema prevents a latent bug when notes flow into generate's update mode.

**Breaking change for existing inbox files:** This renames the field in all new notes. Any existing `notes-inbox.json` with `"id"` fields will break. Since the notes feature is latent (the `id`/`note_id` mismatch means it has never completed a full add→generate round-trip), existing inbox files are unlikely. If any exist, they must be manually updated or cleared.

**Action:** Change `add-note.py` line 78 to write `"note_id"` and line 37 to read `note.get("note_id", "")`. Fix `classify-note.py` line 153 to read `note["note_id"]`. Update all occurrences of `"id"` in `test_add_note.py` (assertions and fixtures) and `test_classify_note.py` fixtures to use `"note_id"`.

### 6. Fix `add-note.py` stdout claim in command file

**File:** `commands/auto-doc-add.md` (was `add-docs.md`, line 66)

The command file tells the LLM: "Capture stdout — it returns JSON with the new `note_id`." But `add-note.py` writes only a human-readable confirmation to stderr (line 96: `print(f"Added note {note_id}: {display_text}", file=sys.stderr)`). No JSON is emitted on stdout. The LLM would attempt to parse non-existent JSON output.

**Action:** Add `print(json.dumps({"note_id": note_id}))` to `add-note.py` before the stderr confirmation (requires `import json`). This makes the command file's claim true. Update `test_add_note.py` to assert stdout contains JSON with the `note_id`.

---

## Scope Summary

| Action | Files |
|--------|-------|
| Rename/move | ~53 files (entire `create-docs/` tree) |
| Delete | 1 file (staleness-scanner.md) |
| Edit (cross-references) | All files containing `create-docs` references (commands, agents, schema, CLAUDE.md, install.sh, mg-install-lib.py) |
| Edit (bug fix) | 7 files (staleness-check.py, add-note.py, classify-note.py, auto-doc-add.md, test_staleness_check.py, test_add_note.py, test_classify_note.py) |
| New | 0 files |
