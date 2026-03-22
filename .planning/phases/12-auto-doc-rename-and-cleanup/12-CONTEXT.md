# Phase 12: Auto Doc Rename and Cleanup - Context

**Gathered:** 2026-03-22 (updated after gray area discussion)
**Status:** Ready for planning
**Source:** Context import + discuss-phase gray area review

<domain>
## Phase Boundary

Rename the tool family from `create-docs` to `auto-doc` and clean up dead code, orphaned agents, and latent bugs discovered during the v1.0 analysis. This clears the deck for all subsequent v1.1 work (phases 13-16).

</domain>

<decisions>
## Implementation Decisions

### Rename strategy
- Clean rename (not symlink or alias) — rename the directory and all files in one pass
- Breaking change — users reinstall via `/mg:install`
- Bulk substitution `s/create-docs/auto-doc/g` handles most renames
- Non-trivial rename: `add-docs` → `auto-doc-add` (verb moves from prefix to suffix) — must be handled explicitly, not by bulk sed

### Command rename map
- `/mg:create-docs` → `/mg:auto-doc`
- `/mg:create-docs-scan` → `/mg:auto-doc-scan`
- `/mg:create-docs-generate` → `/mg:auto-doc-generate`
- `/mg:create-docs-verify` → `/mg:auto-doc-verify`
- `/mg:add-docs` → `/mg:auto-doc-add`

### Directory rename map
- `create-docs/` → `auto-doc/` (entire source tree)
- `create-docs/commands/create-docs.md` → `auto-doc/commands/auto-doc.md` (and so on for all command files)
- `create-docs/commands/add-docs.md` → `auto-doc/commands/auto-doc-add.md`
- `create-docs/agents/`, `scripts/`, `references/`, `install.sh`, `tool.toml` — all move under `auto-doc/`

### Target project paths
- `.claude/commands/mg/create-docs*.md` → `.claude/commands/mg/auto-doc*.md`
- `.claude/create-docs/` → `.claude/auto-doc/`
- `.mg/docs/` remains unchanged (project data, not tool namespace)

### Install infrastructure changes
- `auto-doc/install.sh`: rename `SUPPORT_DIR` from `create-docs` to `auto-doc` (line 172), update `COMMANDS` array entries, update echo statements
- `install/scripts/mg-install-lib.py`: rename workspace mapping `"create-docs": ".mg/docs"` → `"auto-doc": ".mg/docs"` (line 62)

### Migration path in install.sh
1. Before deploying, check for old installation: test if `.claude/commands/mg/create-docs.md` or `.claude/create-docs/` exists
2. If found, remove `.claude/commands/mg/create-docs*.md` and `rm -rf .claude/create-docs/`
3. Remove the stale `create-docs` entry from manifest JSON (`<target>/.claude/mg-tools-manifest.json` — read it, delete the `create-docs` key if present, write it back). `mg-install-lib.py update-manifest` only adds entries; it does not remove old ones.
4. Deploy new `auto-doc` structure as normal
5. Run `mg-install-lib.py update-manifest --tool auto-doc --source <source_dir> --target <target_dir>` to register the new tool

### Internal reference updates
- `{SCRIPTS_DIR}`, `{TEMPLATES_DIR}` etc. stay the same (sed-resolved at install time)
- Command files referencing other commands by name must be updated (e.g., "Run `/mg:create-docs-generate`")
- Agent files referencing command names in their instructions must be updated
- Schema and style guide if they mention command names
- CLAUDE.md in this repo must be updated
- `.planning/` files are historical — don't rename, just update ROADMAP going forward

### Verification
- After rename, grep the ENTIRE repo (not just `auto-doc/`) for remaining `create-docs` or `add-docs` references
- Exclude `.planning/` and `docs/work-queue/` directories (historical docs, don't rename)
- Any hits outside exclusions are bugs

### Delete orphaned staleness-scanner.md
- File: `agents/staleness-scanner.md`
- Never wired into any command; scan pipeline calls `staleness-check.py` directly
- Agent references `--doc-file` parameters that don't exist (scripts use `--docs-dir`)
- `install.sh` uses wildcard copy (`agents/*.md`), so no install script change needed

### Remove dead check-references.py call from scan pipeline
- File: `commands/auto-doc-scan.md` (Step 3: Staleness Check, lines 173-179; also line 290)
- `check-references.py --docs-dir` output is a flat JSON array that fails `merge-scan.py`'s `isinstance(data, dict)` check at line 166
- `merge-scan.py` has no consumer key for reference data — only merges `source_material_index`, `staleness_report`, `note_classifications`, `gap_analysis`, `project_model`, `gsd_context`
- Reference checking is a verify concern, not a scan concern
- Action: remove the invocation from Step 3 and the mention at line 290

### Fix staleness-check.py output format for merge
- File: `scripts/staleness-check.py` (line 275)
- Currently writes flat JSON array via `save_json(args.output, entries)` — silently discarded by `merge-scan.py`'s `isinstance(data, dict)` check
- `merge-scan.py` line 179 expects a `staleness_report` key inside a dict
- Action: wrap CLI output in dict: `save_json(args.output, {"staleness_report": entries})` at line 275
- Internal API (`check_staleness()` function) continues to return a bare list
- Test updates: `TestCLI.test_cli_json_output` (line 334) and `TestCLI.test_cli_output_file` (line 353) — assert `isinstance(data, dict)` with `staleness_report` key
- Function-level tests (`TestStalenessDetection`, `TestSeverity`, `TestOutputFormat`) remain unchanged

### Keep check-references.py for verify pipeline
- After removing scan invocation, `check-references.py` has no scan consumers
- Verify pipeline still depends on it: `auto-doc-verify.md` Step 2 runs `check-references.py --skip-symbol-check --output-broken --output-symbols`
- Phase 14 (reference manifest) will retire this script — no changes needed in Phase 12

### Fix note_id vs id field mismatch
- Python scripts (`add-note.py`, `classify-note.py`) use `"id"` — schema and commands use `"note_id"`
- `"note_id"` wins — the schema is the shared contract, and generate reads `note_id` from `docs-scan.json`
- Action: `add-note.py` line 78 writes `"note_id"`, line 37 reads `note.get("note_id", "")`. `classify-note.py` line 153 reads `note["note_id"]`
- Update all `"id"` occurrences in `test_add_note.py` and `test_classify_note.py` to use `"note_id"`
- Breaking change for any existing `notes-inbox.json` with `"id"` fields — accepted because the feature has never completed a full add→generate round-trip

### Fix add-note.py stdout claim in command file
- `commands/auto-doc-add.md` (line 66) tells the LLM to capture stdout JSON with `note_id`
- `add-note.py` only writes human-readable confirmation to stderr (line 96) — no JSON on stdout
- Action: add `print(json.dumps({"note_id": note_id}))` to `add-note.py` before stderr confirmation (requires `import json`)
- Update `test_add_note.py` to assert stdout contains JSON with `note_id`

### Cross-tool reference updates
- `permission-hooks/hooks/tests/test_permission_guard.py` references `/mg:add-docs` in heredoc test data (lines ~999, 1001, 1033) — update to `/mg:auto-doc-add` for consistency
- `install/commands/install.md` and `.claude/commands/mg/install.md` list `create-docs` in tool listings — update to `auto-doc`

### Non-trivial add-docs → auto-doc-add locations
- `create-docs-generate.md` lines 378, 467, 473: HTML comment template strings `<!-- auto-generated by /mg:create-docs. To add content, use /mg:add-docs. -->` — bulk sed handles `create-docs` → `auto-doc` but `add-docs` → `auto-doc-add` needs explicit substitution in these 3 locations
- Existing generated docs in user projects keep old HTML comments — informational only, no migration needed

### Plan structure
- Plan 1: Rename only (mechanical transformation — directory move, bulk sed, file renames, migration path, verification grep)
- Plan 2: Bug fixes (logic changes to already-renamed files, with tests)
- Rename-first order prevents bulk sed from mangling bug fix text

### Bug fix test strategy
- Run existing test suite as baseline BEFORE any fixes (establish which tests pass/fail)
- Then fix scripts and update tests together
- staleness-check.py: test both layers — CLI tests assert dict wrapper with `staleness_report` key, function-level tests assert bare list return
- Dead check-references.py call removal: add scan pipeline smoke test to verify pipeline still produces valid docs-scan.json after removal
- note_id and add-note.py fixes: update existing test assertions in-place

### Claude's Discretion
- Order of operations within the rename (directory first vs files first)
- Exact error handling for the manifest cleanup in migration path

</decisions>

<specifics>
## Specific Ideas

- The rename follows the pattern established by codebase-health — same install.sh structure, same sed resolution approach
- `add-docs` → `auto-doc-add` is the only command that breaks the naive `s/create-docs/auto-doc/g` pattern — requires explicit handling
- All line number references in bug fixes are from the v1.0 codebase analysis and should be verified against current source before editing

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `install.sh` sed resolution pattern: already handles `{SCRIPTS_DIR}`, `{TEMPLATES_DIR}` — no new placeholders needed
- `mg-install-lib.py` workspace mapping: single line change for the rename
- Wildcard copy in `install.sh` (`agents/*.md`, `scripts/*.py`): deleting `staleness-scanner.md` requires no install script changes

### Established Patterns
- Atomic JSON I/O via `os.replace` and temp files: used by `add-note.py`, `classify-note.py`, `staleness-check.py`
- `merge-scan.py` consumer key pattern: data must be wrapped in a dict with the expected key name
- Test imports via `importlib.machinery.SourceFileLoader`: hyphenated filenames

### Integration Points
- `mg-install-lib.py` workspace mapping (line 62): `create-docs` → `auto-doc`
- `install.sh` SUPPORT_DIR variable (line 172): `create-docs` → `auto-doc`
- `install.sh` COMMANDS array: all entries renamed
- Manifest JSON at target: needs old `create-docs` key removed during migration

</code_context>

<deferred>
## Deferred Ideas

- Phase 13 (auto-doc-script): new `/mg:auto-doc-script` command — depends on rename completing first
- Phase 14 (reference manifest): will retire `check-references.py` — kept alive in Phase 12 for verify pipeline
- Phase 15 (end-user quality): template and writer agent changes — independent of rename
- Phase 16 (incremental scan): `diff-scan.py` and scoped updates — depends on Phase 14

</deferred>

---

*Phase: 12-auto-doc-rename-and-cleanup*
*Context gathered: 2026-03-22 via context import*
