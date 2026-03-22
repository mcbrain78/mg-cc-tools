# Phase 12: Auto Doc Rename and Cleanup - Research

**Researched:** 2026-03-22
**Domain:** Tool rename (directory + namespace), dead code removal, bug fixes in Python scripts and command files
**Confidence:** HIGH

## Summary

Phase 12 is a mechanical rename of the `create-docs` tool family to `auto-doc`, combined with cleanup of dead code and fixing latent bugs discovered during v1.0 analysis. The CONTEXT.md provides extraordinarily detailed decisions -- line numbers, exact rename maps, specific field names, and test update instructions. This is a well-defined, low-ambiguity phase.

The rename is a clean break (not aliases or symlinks). The 5 commands map as: `create-docs` -> `auto-doc`, `create-docs-scan` -> `auto-doc-scan`, `create-docs-generate` -> `auto-doc-generate`, `create-docs-verify` -> `auto-doc-verify`, `add-docs` -> `auto-doc-add`. The `add-docs` -> `auto-doc-add` rename is the only non-trivial one because it breaks the naive `s/create-docs/auto-doc/g` pattern and requires explicit substitution.

**Primary recommendation:** Execute as two plans: Plan 1 (rename-only, mechanical transformation), Plan 2 (bug fixes on already-renamed files). This order prevents bulk sed from mangling bug fix text.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Clean rename (not symlink or alias) -- rename the directory and all files in one pass
- Breaking change -- users reinstall via `/mg:install`
- Bulk substitution `s/create-docs/auto-doc/g` handles most renames
- Non-trivial rename: `add-docs` -> `auto-doc-add` (verb moves from prefix to suffix) -- must be handled explicitly, not by bulk sed
- Command rename map:
  - `/mg:create-docs` -> `/mg:auto-doc`
  - `/mg:create-docs-scan` -> `/mg:auto-doc-scan`
  - `/mg:create-docs-generate` -> `/mg:auto-doc-generate`
  - `/mg:create-docs-verify` -> `/mg:auto-doc-verify`
  - `/mg:add-docs` -> `/mg:auto-doc-add`
- Directory rename map:
  - `create-docs/` -> `auto-doc/` (entire source tree)
  - `create-docs/commands/create-docs.md` -> `auto-doc/commands/auto-doc.md` (and so on for all command files)
  - `create-docs/commands/add-docs.md` -> `auto-doc/commands/auto-doc-add.md`
  - `create-docs/agents/`, `scripts/`, `references/`, `install.sh`, `tool.toml` -- all move under `auto-doc/`
- Target project paths: `.claude/commands/mg/create-docs*.md` -> `.claude/commands/mg/auto-doc*.md`, `.claude/create-docs/` -> `.claude/auto-doc/`
- Install infrastructure: `auto-doc/install.sh` rename SUPPORT_DIR from `create-docs` to `auto-doc`, update COMMANDS array, update echo statements
- `install/scripts/mg-install-lib.py`: rename workspace mapping `"create-docs": ".mg/docs"` -> `"auto-doc": ".mg/docs"`
- Migration path in install.sh: check for old installation, remove old files, clean manifest, deploy new structure
- `.planning/` files are historical -- don't rename, just update ROADMAP going forward
- Exclude `.planning/` and `docs/work-queue/` from verification grep (historical docs)
- Delete orphaned `agents/staleness-scanner.md`
- Remove dead `check-references.py` call from scan pipeline (Step 3, lines 173-179 and line 290)
- Fix `staleness-check.py` output format: wrap CLI output in `{"staleness_report": entries}` at line 275
- Keep `check-references.py` for verify pipeline (Phase 14 retires it)
- Fix `note_id` vs `id` field mismatch: `"note_id"` wins (schema is shared contract)
- Fix `add-note.py` stdout: add `print(json.dumps({"note_id": note_id}))` before stderr confirmation
- Cross-tool reference updates: `permission-hooks/hooks/tests/test_permission_guard.py`, `install/commands/install.md`, `.claude/commands/mg/install.md`
- Non-trivial `add-docs` -> `auto-doc-add` locations: `create-docs-generate.md` lines 378, 467, 473 HTML comment template strings
- Plan structure: Plan 1 (rename only), Plan 2 (bug fixes)
- Rename-first order prevents bulk sed from mangling bug fix text
- Bug fix test strategy: run baseline before fixes, then fix scripts and update tests together

### Claude's Discretion
- Order of operations within the rename (directory first vs files first)
- Exact error handling for the manifest cleanup in migration path

### Deferred Ideas (OUT OF SCOPE)
- Phase 13 (auto-doc-script): new `/mg:auto-doc-script` command -- depends on rename completing first
- Phase 14 (reference manifest): will retire `check-references.py` -- kept alive in Phase 12 for verify pipeline
- Phase 15 (end-user quality): template and writer agent changes -- independent of rename
- Phase 16 (incremental scan): `diff-scan.py` and scoped updates -- depends on Phase 14
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| git mv | (system) | Directory and file renames with history tracking | Preserves git blame and history across renames |
| sed | (system) | Bulk text substitution in renamed files | Handles `s/create-docs/auto-doc/g` and explicit `add-docs` -> `auto-doc-add` |
| Python 3.11+ | >=3.11 | Script fixes (staleness-check, add-note, classify-note) | Already the project floor (set in Phase 7) |
| pytest | >=9.0 | Test suite execution for bug fix verification | Already in dev dependencies |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | N/A | JSON stdout output from add-note.py | For the note_id fix |
| subprocess | N/A | CLI test invocations | Existing test pattern |

No new dependencies are introduced by this phase.

## Architecture Patterns

### Recommended Rename Order

The rename should proceed directory-first, then file renames, then content substitution:

```
Step 1: git mv create-docs/ auto-doc/        # Directory rename
Step 2: Rename command files inside auto-doc/commands/
        - create-docs.md -> auto-doc.md
        - create-docs-scan.md -> auto-doc-scan.md
        - create-docs-generate.md -> auto-doc-generate.md
        - create-docs-verify.md -> auto-doc-verify.md
        - add-docs.md -> auto-doc-add.md         # Non-trivial rename
Step 3: Delete orphaned staleness-scanner.md
Step 4: Bulk sed s/create-docs/auto-doc/g on all files under auto-doc/
Step 5: Explicit sed s/add-docs/auto-doc-add/g on specific locations
Step 6: Update cross-tool references outside auto-doc/
Step 7: Verification grep
```

### File Inventory (Verified Against Current Codebase)

**Files inside `create-docs/` (will become `auto-doc/`):**

Commands (5 files -- 5 renames):
- `commands/create-docs.md` -> `commands/auto-doc.md`
- `commands/create-docs-scan.md` -> `commands/auto-doc-scan.md`
- `commands/create-docs-generate.md` -> `commands/auto-doc-generate.md`
- `commands/create-docs-verify.md` -> `commands/auto-doc-verify.md`
- `commands/add-docs.md` -> `commands/auto-doc-add.md`

Agents (9 files -- 1 deleted, 8 unchanged filenames):
- `agents/staleness-scanner.md` -- **DELETE** (orphaned, never wired)
- `agents/agent-writer.md` -- no rename needed
- `agents/developer-writer.md` -- no rename needed
- `agents/devops-writer.md` -- no rename needed
- `agents/end-user-writer.md` -- no rename needed
- `agents/glossary-writer.md` -- no rename needed
- `agents/scan-audience.md` -- no rename needed
- `agents/TEMPLATE.md` -- no rename needed
- `agents/verifier.md` -- no rename needed

Scripts (11 .py files + 2 lib files + 8 test files -- no renames, only content fixes):
- Scripts retain their filenames (add-note.py, staleness-check.py, etc.)
- Tests retain their filenames

References (15 files -- no renames):
- `references/schema.md` -- content update needed
- `references/style-guide.md` -- content update needed
- `references/.docs.config.json` -- no change
- `references/templates/**` -- no changes

Other:
- `install.sh` -- content rewrite (SUPPORT_DIR, COMMANDS array, echo strings, migration path)
- `tool.toml` -- content update ([detect].paths)

**Files outside `create-docs/` needing content updates:**
- `install/scripts/mg-install-lib.py` line 62: workspace mapping key
- `install/commands/install.md` line 108: tool listing
- `.claude/commands/mg/install.md` line 108: tool listing (installed copy)
- `permission-hooks/hooks/tests/test_permission_guard.py` lines ~999, 1001, 1033: test data

**Files explicitly excluded from rename (historical):**
- Everything under `.planning/` (97 files with matches)
- Everything under `docs/work-queue/` (8 files with matches)

### Content Substitution Strategy

**Bulk sed** (`s/create-docs/auto-doc/g`) handles:
- All command name references (`/mg:create-docs` -> `/mg:auto-doc`)
- Directory path references (`.claude/create-docs/` -> `.claude/auto-doc/`)
- Docstrings and comments mentioning `create-docs`
- YAML frontmatter (`name: mg:create-docs-*` -> `name: mg:auto-doc-*`)
- Install.sh variable names and echo strings

**Explicit substitution** (`s/add-docs/auto-doc-add/g`) handles:
- Command references (`/mg:add-docs` -> `/mg:auto-doc-add`)
- `create-docs-generate.md` HTML comments at lines 378, 467, 473
- Permission-hooks test data
- Install.md tool listings

**Order matters:** Run `s/add-docs/auto-doc-add/g` BEFORE `s/create-docs/auto-doc/g` to prevent `add-docs` from being caught by the broader pattern. Or run it after on a second pass -- either works since `add-docs` does not contain `create-docs` as a substring.

Actually, since `add-docs` is NOT a substring of `create-docs`, the order between these two substitutions does not matter. They are independent patterns.

### Bug Fix Patterns

**Pattern: Wrap CLI output in dict for merge compatibility**

staleness-check.py currently at line 275:
```python
# Current (broken for merge-scan.py):
save_json(args.output, entries)

# Fixed:
save_json(args.output, {"staleness_report": entries})
```

The internal `check_staleness()` function continues returning a bare list. Only the CLI output path changes.

**Pattern: Field name normalization to match schema**

add-note.py currently uses `"id"` at lines 37 and 78. Schema uses `"note_id"`:
```python
# Current:
note = {"id": note_id, ...}
note.get("id", "")

# Fixed:
note = {"note_id": note_id, ...}
note.get("note_id", "")
```

classify-note.py at line 153 also reads `note["id"]`:
```python
# Current:
if note["id"] == args.note_id:

# Fixed:
if note["note_id"] == args.note_id:
```

**Pattern: Add JSON stdout output**

add-note.py currently only writes to stderr. The command file expects JSON on stdout:
```python
# Add before stderr confirmation (line 96):
import json  # (add to imports)
print(json.dumps({"note_id": note_id}))
```

### Migration Path in install.sh

The install.sh needs a migration section before the normal install flow:
```bash
# Check for old installation
if [[ -f "${COMMANDS_DIR}/create-docs.md" ]] || [[ -d "${TARGET_DIR}/create-docs" ]]; then
    echo "  Migrating from create-docs to auto-doc ..."
    rm -f "${COMMANDS_DIR}"/create-docs*.md
    rm -f "${COMMANDS_DIR}"/add-docs.md
    rm -rf "${TARGET_DIR}/create-docs"
    # Clean manifest
    # (use python3 to read JSON, delete create-docs key, write back)
fi
```

### Anti-Patterns to Avoid
- **Running bulk sed on historical directories:** `.planning/` and `docs/work-queue/` must be excluded -- these are historical records
- **Renaming `add-docs` with the `create-docs` pattern:** `s/create-docs/auto-doc/g` will NOT catch `add-docs` references -- they need explicit handling
- **Fixing bugs before rename:** Bug fix text (like `"staleness_report"`) could get mangled by the bulk sed if present in wrong context. Rename first, then fix.
- **Editing `check-references.py` itself:** It is kept alive for the verify pipeline. Only its invocation in the scan command is removed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Directory rename | Manual cp + rm | `git mv create-docs auto-doc` | Preserves git history and blame |
| Manifest JSON cleanup | Inline bash jq | Python one-liner via `json` stdlib | More reliable for nested JSON, jq may not be installed |
| Bulk text substitution | Python script | `sed -i` with explicit patterns | Simpler, well-understood, matches project conventions |

## Common Pitfalls

### Pitfall 1: The add-docs -> auto-doc-add Non-Trivial Rename
**What goes wrong:** Naive `s/create-docs/auto-doc/g` misses all `add-docs` references entirely, leaving broken command references scattered across the codebase.
**Why it happens:** `add-docs` does not contain the substring `create-docs`, so it is invisible to the bulk pattern.
**How to avoid:** After bulk sed, run explicit `s/add-docs/auto-doc-add/g` on the known locations (3 locations in generate command, permission-hooks tests, install.md). Then verification grep catches any missed spots.
**Warning signs:** Post-rename grep finds `add-docs` outside exclusion directories.

### Pitfall 2: Installed Copy of install.md
**What goes wrong:** Updating `install/commands/install.md` but forgetting `.claude/commands/mg/install.md` (the installed copy in this repo).
**Why it happens:** The source and installed copy are separate files, not symlinked.
**How to avoid:** The CONTEXT.md already flags both locations. Update both.
**Warning signs:** Post-rename grep finds `create-docs` in `.claude/` directory.

### Pitfall 3: __pycache__ and .pyc Files
**What goes wrong:** `git mv` moves the directory including `__pycache__/` directories, which then have stale bytecode.
**Why it happens:** Python caches compiled bytecode with embedded paths.
**How to avoid:** After directory rename, delete all `__pycache__/` directories under `auto-doc/`. They regenerate on next import. These should not be in git anyway (check .gitignore).
**Warning signs:** Import errors or stale module paths in test runs.

### Pitfall 4: Verification Grep Scope
**What goes wrong:** Grep for `create-docs` finds hundreds of matches in `.planning/` and panics.
**Why it happens:** Historical documents legitimately reference the old name.
**How to avoid:** Exclude `.planning/` and `docs/work-queue/` from verification. The CONTEXT.md already specifies this. Use: `grep -r "create-docs\|add-docs" --exclude-dir=.planning --exclude-dir=docs --exclude-dir=.git .`
**Warning signs:** Large match count in verification step.

### Pitfall 5: staleness-check.py Dual Output Paths
**What goes wrong:** Fixing the `--output` path but not the stdout path, or vice versa.
**Why it happens:** The script has two output paths: `save_json()` for `--output` flag and `json.dump()` for stdout.
**How to avoid:** Per CONTEXT.md, only the `--output` path (save_json at line 275) wraps in dict. The stdout path (json.dump at line 277) should also wrap for consistency, OR the decision is to only wrap the file output. Verify against merge-scan.py consumption pattern -- merge reads files from `scan-logs/`, not stdout.
**Warning signs:** Tests pass for file output but stdout produces different format.

### Pitfall 6: YAML Frontmatter Name Field
**What goes wrong:** Bulk sed renames the command filename but misses the `name:` field in YAML frontmatter.
**Why it happens:** Forgetting that command files have both a filename and an internal name declaration.
**How to avoid:** The bulk `s/create-docs/auto-doc/g` handles `name: mg:create-docs*` lines naturally. The `add-docs` frontmatter needs explicit handling: `name: mg:add-docs` -> `name: mg:auto-doc-add`.
**Warning signs:** Command invocation name doesn't match filename after rename.

## Code Examples

### Example: staleness-check.py CLI Output Fix

```python
# Source: CONTEXT.md line 82, verified against staleness-check.py line 275

# Before (line 275):
save_json(args.output, entries)

# After:
save_json(args.output, {"staleness_report": entries})
```

Test updates needed in `test_staleness_check.py`:
```python
# test_cli_json_output (line 334) -- currently asserts isinstance(data, list)
# Change to:
data = json.loads(result.stdout)
assert isinstance(data, dict)
assert "staleness_report" in data
assert isinstance(data["staleness_report"], list)

# test_cli_output_file (line 353) -- currently asserts isinstance(data, list)
# Change to:
data = json.loads(output_file.read_text())
assert isinstance(data, dict)
assert "staleness_report" in data
assert isinstance(data["staleness_report"], list)
```

### Example: add-note.py note_id and stdout fixes

```python
# Source: CONTEXT.md lines 93-103, verified against add-note.py

# Fix 1: note_id field name (line 37)
match = re.match(r"NOTE-(\d+)", note.get("note_id", ""))

# Fix 2: note_id field name (line 78)
note = {
    "note_id": note_id,  # was "id"
    "text": args.text,
    ...
}

# Fix 3: JSON stdout output (before line 96)
import json  # add to imports at top
print(json.dumps({"note_id": note_id}))
print(f"Added note {note_id}: {display_text}", file=sys.stderr)
```

### Example: classify-note.py note_id fix

```python
# Source: CONTEXT.md line 95, verified against classify-note.py line 153

# Before:
if note["id"] == args.note_id:

# After:
if note["note_id"] == args.note_id:
```

### Example: Migration Path in install.sh

```bash
# Source: CONTEXT.md lines 46-51

# -- Migration from create-docs to auto-doc -----------------------------------
MANIFEST_FILE="$(dirname "$TARGET_DIR")/.claude/mg-tools-manifest.json"

if [[ -f "${COMMANDS_DIR}/create-docs.md" ]] || [[ -d "${TARGET_DIR}/create-docs" ]]; then
    echo "  Migrating: removing old create-docs installation ..."
    rm -f "${COMMANDS_DIR}/create-docs.md" \
          "${COMMANDS_DIR}/create-docs-scan.md" \
          "${COMMANDS_DIR}/create-docs-generate.md" \
          "${COMMANDS_DIR}/create-docs-verify.md" \
          "${COMMANDS_DIR}/add-docs.md"
    rm -rf "${TARGET_DIR}/create-docs"

    # Remove stale manifest entry
    if [[ -f "$MANIFEST_FILE" ]]; then
        python3 -c "
import json, sys
p = '$MANIFEST_FILE'
with open(p) as f: m = json.load(f)
m.pop('create-docs', None)
with open(p, 'w') as f: json.dump(m, f, indent=2)
" 2>/dev/null || echo "  Warning: could not clean manifest (non-fatal)"
    fi
fi
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `create-docs` namespace | `auto-doc` namespace | Phase 12 (this phase) | All command names change, users must reinstall |
| `"id"` field in notes | `"note_id"` field | Phase 12 (this phase) | Breaking for existing `notes-inbox.json` with `"id"` fields (accepted: feature never completed full round-trip) |
| `staleness-check.py` flat array output | Dict-wrapped `{"staleness_report": [...]}` output | Phase 12 (this phase) | Enables merge-scan.py to consume staleness data |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ |
| Config file | pyproject.toml (project root) |
| Quick run command | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| Full suite command | `python3 -m pytest --tb=short -q --no-header` |

### Phase Requirements -> Test Map

No formal requirement IDs are assigned to Phase 12. The requirements are implicit from CONTEXT.md. Below maps the behavioral requirements to tests:

| Behavior | Test Type | Automated Command | File Exists? |
|----------|-----------|-------------------|-------------|
| staleness-check.py CLI outputs dict with `staleness_report` key | unit | `python3 -m pytest auto-doc/scripts/tests/test_staleness_check.py::TestCLI::test_cli_json_output -x` | Exists (needs update) |
| staleness-check.py --output writes dict with `staleness_report` key | unit | `python3 -m pytest auto-doc/scripts/tests/test_staleness_check.py::TestCLI::test_cli_output_file -x` | Exists (needs update) |
| add-note.py uses `note_id` field (not `id`) | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_note.py -x` | Exists (needs update) |
| add-note.py outputs JSON with `note_id` to stdout | unit | `python3 -m pytest auto-doc/scripts/tests/test_add_note.py::TestAddNoteBasic::test_append_to_empty_inbox -x` | Exists (needs new assertion) |
| classify-note.py reads `note_id` from inbox | unit | `python3 -m pytest auto-doc/scripts/tests/test_classify_note.py -x` | Exists (needs update) |
| All existing tests pass after rename | regression | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` | Exists |
| No `create-docs` or `add-docs` references outside exclusions | smoke | Manual grep verification | N/A (manual) |

### Baseline
- **Current test count:** 105 tests, all passing (verified 2026-03-22)
- **Test location:** `create-docs/scripts/tests/` (will become `auto-doc/scripts/tests/`)

### Sampling Rate
- **Per task commit:** `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header`
- **Per wave merge:** `python3 -m pytest --tb=short -q --no-header` (full project suite)
- **Phase gate:** Full suite green + verification grep clean

### Wave 0 Gaps
- [ ] Add test for `add-note.py` JSON stdout output (new behavior, needs new test assertion)
- [ ] Add scan pipeline smoke test to verify `docs-scan.json` production still works after removing `check-references.py` call (CONTEXT.md line 122)

## Open Questions

1. **staleness-check.py stdout vs file output consistency**
   - What we know: CONTEXT.md says to wrap `save_json(args.output, ...)` at line 275. The stdout path (line 277) is not mentioned.
   - What's unclear: Should stdout also wrap in `{"staleness_report": entries}` for consistency, or remain a flat list since no consumer reads stdout?
   - Recommendation: Wrap both for consistency. The stdout path is used for debugging/manual inspection, and having different formats between `--output` and stdout is confusing. However, this is a discretionary choice -- the critical fix is the `--output` path which merge-scan.py reads.

2. **Manifest cleanup error handling**
   - What we know: CONTEXT.md says to remove the `create-docs` key from manifest JSON. `mg-install-lib.py update-manifest` only adds entries.
   - What's unclear: Exact error handling if manifest is malformed or missing.
   - Recommendation: Best-effort with `2>/dev/null || echo "Warning: ..."`. The manifest is rewritten by `update-manifest` after install anyway, so a failed cleanup is non-fatal. This is in Claude's discretion per CONTEXT.md.

## Sources

### Primary (HIGH confidence)
- `create-docs/` directory listing and file contents (verified via Read/Grep tools)
- `12-CONTEXT.md` -- comprehensive decisions document with line-number precision
- `create-docs/scripts/tests/` -- baseline test suite (105 tests passing)
- `install/scripts/mg-install-lib.py` line 62 -- workspace mapping verified
- `permission-hooks/hooks/tests/test_permission_guard.py` lines 999, 1001, 1033 -- cross-tool references verified
- `install/commands/install.md` line 108 and `.claude/commands/mg/install.md` line 108 -- tool listing verified

### Secondary (MEDIUM confidence)
- Line number references from CONTEXT.md for bug fixes -- verified against current source but could drift if other changes land before Phase 12 executes

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all tools already in use
- Architecture: HIGH - rename map is explicit, file inventory verified against codebase
- Pitfalls: HIGH - all identified from concrete codebase analysis, not hypothetical
- Bug fixes: HIGH - line numbers verified against current source, test assertions confirmed

**Research date:** 2026-03-22
**Valid until:** 2026-04-05 (stable -- only invalidated if someone modifies create-docs/ before Phase 12 executes)
