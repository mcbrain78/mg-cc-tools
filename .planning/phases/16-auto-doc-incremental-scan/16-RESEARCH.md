# Phase 16: Auto Doc Incremental Scan - Research

**Researched:** 2026-03-22
**Domain:** Incremental documentation scanning via git diff, GSD phase summaries, and reference manifests
**Confidence:** HIGH

## Summary

Phase 16 adds an incremental scan mode to the auto-doc pipeline. Instead of re-scanning the entire codebase every time, the system uses git diff to identify changed files, cross-references them against reference manifests to identify affected documentation sections, and enriches the scope with GSD phase context. This produces a `diff-scope.json` work order that scan agents consume to analyze only what changed.

The core new artifact is `diff-scan.py`, a deterministic Python script (~200-250 lines) that requires no LLM. It reads git history, reference manifests, and optionally GSD phase summaries, then outputs a scoped work order. The scan command (`auto-doc-scan.md`) and scan-audience agent (`scan-audience.md`) need modifications to detect incremental mode, pass scoped data, and carry forward unchanged entries. The router (`auto-doc.md`) needs minor updates to reflect incremental capabilities.

**Primary recommendation:** Build `diff-scan.py` first with comprehensive tests, then modify the scan command and agent to consume its output. All changes extend existing patterns -- no new architectural concepts needed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Two cycles:** Initial (full scan, unchanged pipeline) vs incremental (scoped scan based on diff). Scan command auto-detects which mode based on docs/manifests/`last_generated` existence.
- **Three change signal sources:** Git (authoritative file changes), GSD (contextual why), Code (structural how -- agents read only changed files).
- **diff-scan.py:** Deterministic Python script, no LLM. CLI: `--project-root`, `--manifests-dir`, `--docs-dir`, `--since`, `--gsd-dir`, `--output`. Output to `.mg/docs/diff-scope.json` (NOT `scan-logs/`).
- **diff-scope.json format:** Top-level fields: `since`, `summary`, `affected_sections`, `new_file_candidates`, `deleted_files`, `gsd_phases_since`. Each `affected_sections` entry: `{audience, document, section, reason, changed_files, gsd_context}`.
- **diff-scan.py processing steps:** (1) resolve timestamp to commit via `git rev-list`, diff with `-M`; (2) cross-reference changed files against manifests; (3) discover GSD phases; (4) classify results.
- **Timestamp source:** Single global `last_generated` ISO timestamp in `docs-scan.json` (not per-audience, not commit SHA). Written by generate at pipeline start. Over-inclusive by design.
- **Rename detection:** Both git commands use `-M`. Separate `git diff -M --diff-filter=R --name-status` extracts rename pairs. Script parses `R<score>\told\tnew`.
- **Carry-forward strategy:** Scan command loads previous `docs-scan.json`, filters by audience, passes unchanged entries as baseline. Agent writes complete output (changed + carried-forward).
- **GSD optional:** If `--gsd-dir` does not exist, skip GSD entirely. `gsd_phases_since: []`, all `gsd_context: null`. No error.
- **New file candidates:** Auto-classified by scan agents into existing sections. Tagged `"source": "incremental"`. No user approval step.
- **Cross-audience impact:** Diff script reads all audience manifests, emits one entry per audience x document x section combination.
- **Staleness check relationship:** In incremental mode, diff-scan.py replaces staleness check's scoping role. Staleness continues as post-generate validation.
- **Verify unchanged:** Runs in full on every cycle. No scoping needed.
- **Incremental scan summary UX:** Show diff-focused summary after scan completes (not full project model). N files changed, N sections affected, N new files, N deleted references.
- **Full-scan escape hatch:** No `--full` flag. Delete `docs/auto-doc/` and `.mg/docs/docs-scan.json` to force full scan. No threshold-based fallback.
- **No migration path:** Old docs deleted before adopting incremental scan. Missing `last_generated` = initial mode.

### Claude's Discretion
- Internal architecture of `diff-scan.py` (class structure, helper functions)
- Test fixture design and sample data for diff-scope tests
- How to present incremental mode detection in the router (messaging, suggestions)
- Error handling for edge cases (corrupt manifests, missing git history, timestamp before any commits)
- Whether to add a `--dry-run` mode to diff-scan.py for previewing scope without running scan
- How to structure the incremental mode prompt additions in scan-audience.md

### Deferred Ideas (OUT OF SCOPE)
None -- source document covers phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ISC-01 | Scan command detects initial vs incremental mode based on docs/manifests/`last_generated`; incremental always used when conditions met | Mode detection logic in auto-doc-scan.md Step 12 extension; check `last_generated` field in docs-scan.json, manifests in `.mg/docs/reference-manifests/`, docs in `docs_dir` |
| ISC-02 | diff-scan.py produces diff-scope.json by cross-referencing git diff against manifests, with GSD context | New script using `lib/git_helpers` + `lib/json_io`, manifest JSON parsing, git subprocess calls |
| ISC-03 | Git rename detection produces single entries, prevents false broken-reference reports | `git diff -M --diff-filter=R --name-status` parses `R<score>\told\tnew` format; verified working |
| ISC-04 | Incremental scan agents receive only changed sections + carried-forward baseline | Scan command filters previous docs-scan.json by audience; agent prompt extension in scan-audience.md |
| ISC-05 | New files auto-classified by scan agents, tagged as incremental additions | `"source": "incremental"` tag on new source_material_index entries; no write-scan-output.py changes needed (extra fields pass through) |
| ISC-06 | GSD context optional -- empty context when no GSD directory exists | `--gsd-dir` existence check; `gsd_phases_since: []` and `gsd_context: null` |
| ISC-07 | Diff-focused summary shown after incremental scan | Scan command reads diff-scope.json summary for UX display instead of full project model |
| ISC-08 | Verify step runs in full on every cycle regardless of scan mode | No changes needed -- verify already runs unconditionally |
| ISC-09 | Full re-scan by deleting docs dir and docs-scan.json -- no flag or threshold | Mode detection falls back to initial when `last_generated` missing; no code changes needed for this requirement beyond correct mode detection |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `subprocess` | 3.12+ | Git command execution | Existing pattern in `lib/git_helpers.py` and `staleness-check.py` |
| Python stdlib `json` | 3.12+ | Manifest and scope JSON I/O | Existing pattern via `lib/json_io.py` |
| Python stdlib `os` / `pathlib` | 3.12+ | File path operations | Existing pattern throughout scripts |
| Python stdlib `argparse` | 3.12+ | CLI argument parsing | Existing pattern in all pipeline scripts |
| `lib/json_io.py` | internal | Atomic JSON load/save | Shared utility across all auto-doc scripts |
| `lib/git_helpers.py` | internal | Git subprocess wrappers | Shared utility; has `git_log_since`, `git_file_changed_since`, `git_last_modified` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | dev dep | Test framework | Test diff-scan.py with git repo fixtures |
| `importlib.machinery` | stdlib | Import hyphenated modules in tests | Test imports for `diff-scan.py` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| subprocess for git | GitPython / pygit2 | External dependency; subprocess is the established pattern and sufficient |
| pathlib | os.path | Either works; use os.path to match existing scripts |

**Installation:**
No new dependencies. Everything is stdlib + existing internal libraries.

## Architecture Patterns

### Recommended Project Structure
```
auto-doc/
├── scripts/
│   ├── diff-scan.py              # NEW: deterministic diff scoping script
│   ├── lib/
│   │   ├── git_helpers.py        # EXTEND: add git_diff_names, git_diff_renames, git_resolve_commit
│   │   └── json_io.py            # UNCHANGED
│   ├── merge-scan.py             # UNCHANGED
│   ├── staleness-check.py        # UNCHANGED
│   └── tests/
│       └── test_diff_scan.py     # NEW: comprehensive diff-scan tests
├── commands/
│   ├── auto-doc-scan.md          # MODIFY: add incremental mode detection + scoped agent dispatch
│   └── auto-doc.md               # MODIFY: update router Route D for incremental mention
├── agents/
│   └── scan-audience.md          # MODIFY: handle incremental mode inputs + carry-forward
└── references/
    └── schema.md                 # MODIFY: add last_generated field, diff-scope.json docs
```

### Pattern 1: Deterministic Script with Git Subprocess
**What:** `diff-scan.py` follows the same pattern as `staleness-check.py` -- a standalone script that uses git subprocess calls for deterministic analysis.
**When to use:** When the operation is fully deterministic (no LLM needed) and produces structured JSON output.
**Example:**
```python
# Pattern from staleness-check.py and git_helpers.py
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.json_io import load_json, save_json

def resolve_commit(since_timestamp, project_root):
    """Resolve ISO timestamp to the nearest commit before that time."""
    cmd = [
        "git", "rev-list", "--max-count=1",
        f"--before={since_timestamp}", "HEAD",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", cwd=project_root,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()

def get_changed_files(base_commit, project_root):
    """Get files changed between base_commit and HEAD."""
    cmd = [
        "git", "diff", "-M", "--name-only",
        base_commit, "HEAD",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", cwd=project_root,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f.strip()]

def get_renames(base_commit, project_root):
    """Get rename pairs between base_commit and HEAD."""
    cmd = [
        "git", "diff", "-M", "--diff-filter=R",
        "--name-status", base_commit, "HEAD",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", cwd=project_root,
    )
    if result.returncode != 0:
        return {}
    renames = {}
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            renames[parts[1]] = parts[2]  # old -> new
    return renames
```

### Pattern 2: Manifest Cross-Referencing
**What:** Read per-audience manifest JSON files and build a reverse index from file paths to (audience, document, section) tuples.
**When to use:** When determining which documentation sections are affected by a set of changed files.
**Example:**
```python
def build_file_to_sections_index(manifests_dir):
    """Build reverse index: file_path -> list of (audience, document, section)."""
    index = {}
    manifest_files = glob.glob(os.path.join(manifests_dir, "*.json"))
    for mf in manifest_files:
        manifest = load_json(mf)
        if not manifest or "documents" not in manifest:
            continue
        audience = manifest.get("audience", os.path.splitext(os.path.basename(mf))[0])
        for doc_name, sections in manifest["documents"].items():
            for section_slug, section_data in sections.items():
                if section_slug == "_written_sections":
                    continue  # Skip metadata entries
                for fp in section_data.get("file_paths", []):
                    if fp not in index:
                        index[fp] = []
                    index[fp].append({
                        "audience": audience,
                        "document": doc_name,
                        "section": section_slug,
                    })
    return index
```

### Pattern 3: Carry-Forward in Scan Command
**What:** The scan command loads previous `docs-scan.json`, extracts per-audience source material entries, and passes unchanged entries to each scan agent as baseline data.
**When to use:** Incremental mode -- agents write complete output (new analysis + carried-forward entries).
**Example (conceptual, for scan-audience.md agent prompt):**
```
Mode: incremental
Changed files: [list from diff-scope.json filtered by this audience]
GSD context: [from diff-scope.json]

Baseline entries (copy these VERBATIM into your output for sections NOT listed above):
{
  "ARCHITECTURE/data-model": {
    "source_files": ["src/db/models.py"],
    "staleness": "unknown"
  },
  ...
}

New file candidates to classify: [list from diff-scope.json]
```

### Anti-Patterns to Avoid
- **Writing diff-scope.json to scan-logs/:** Would be picked up by merge-scan.py which reads all `*.json` in `scan-logs/`. Must go to `.mg/docs/diff-scope.json`.
- **Using commit SHA instead of timestamp:** Commits can be lost during squash & merge. Timestamps are robust.
- **Per-audience timestamps:** Creates complexity for no benefit. A single global `last_generated` is simpler and over-inclusive by design.
- **Skipping carry-forward:** If agents only return changed entries, merge-scan.py would lose unchanged entries, breaking the pipeline.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic JSON I/O | Custom file writing | `lib/json_io.save_json()` | Handles temp file + os.replace atomically |
| Git subprocess calls | Raw subprocess.run for common ops | `lib/git_helpers.py` functions | Established pattern, handles errors consistently |
| Scan output validation | Manual JSON structure checks | `write-scan-output.py` | Already validates key format and required fields |
| Manifest parsing | Custom JSON parsing | `lib/json_io.load_json()` | Handles missing files gracefully with default |

**Key insight:** The existing `lib/` directory provides all the building blocks. New git helpers (resolve_commit, diff_names, diff_renames) should be added to `lib/git_helpers.py` to keep the pattern consistent -- but this is a discretion area, as the CONTEXT.md says internal architecture is Claude's discretion. An alternative is to keep the git logic inside `diff-scan.py` itself if it keeps the module more self-contained.

## Common Pitfalls

### Pitfall 1: diff-scope.json in scan-logs/
**What goes wrong:** If `diff-scope.json` is written to `.mg/docs/scan-logs/`, `merge-scan.py` will read it (it globs all `*.json` in that directory) and try to merge its `affected_sections` array as if it were scan output.
**Why it happens:** Natural instinct to put pipeline intermediates in scan-logs.
**How to avoid:** Write to `.mg/docs/diff-scope.json` (parent directory, not scan-logs/).
**Warning signs:** merge-scan.py warnings about unexpected fields; corrupt docs-scan.json with affected_sections at top level.

### Pitfall 2: Timestamp-to-Commit Resolution Edge Cases
**What goes wrong:** `git rev-list --max-count=1 --before=<timestamp> HEAD` returns nothing if the timestamp is before the first commit, or returns an unexpected commit if the repository was force-pushed or rebased.
**Why it happens:** The timestamp-to-commit conversion is an approximation by design.
**How to avoid:** Handle empty `git rev-list` output gracefully -- fall back to initial mode. Log a message: "Could not resolve timestamp to commit, falling back to full scan."
**Warning signs:** Empty base commit; diff returning the entire repository history.

### Pitfall 3: Manifest file_paths vs Changed Files Path Format
**What goes wrong:** Manifests store file paths relative to project root (e.g., `src/models.py`), and git diff also reports relative paths -- but git may use different separators or prefixes depending on configuration.
**Why it happens:** Git diff output is sensitive to core.quotePath settings and path encoding.
**How to avoid:** Normalize all paths to forward-slash relative paths before comparison. Strip any leading `./` from both sides.
**Warning signs:** Changed files not matching any manifest entries despite being referenced.

### Pitfall 4: Rename Detection False Positives
**What goes wrong:** Git's rename detection with `-M` uses similarity thresholds. A file deletion + unrelated new file with similar content could be falsely detected as a rename.
**Why it happens:** Git uses content similarity for rename detection (default threshold: 50%).
**How to avoid:** Accept the default behavior -- git's heuristic is good enough. The over-inclusive approach means a false rename is harmless (section gets re-scanned).
**Warning signs:** Unlikely to cause issues in practice.

### Pitfall 5: Circular Reference Between docs-scan.json Reading and Writing
**What goes wrong:** In incremental mode, the scan command reads `docs-scan.json` for baseline entries, then merge-scan.py overwrites the same file with merged results. If the read happens after the merge, baseline data is lost.
**Why it happens:** Both operations target the same file.
**How to avoid:** Read the previous `docs-scan.json` BEFORE clearing scan-logs (which is already Step 13 in the scan command). Store the baseline entries in memory. The merge creates a new `docs-scan.json` from scan-logs output.
**Warning signs:** All sections appearing as "unknown" in incremental mode.

### Pitfall 6: GSD Summary File Discovery
**What goes wrong:** The script looks for `*-SUMMARY.md` files in GSD phases that were modified since the last generation. If it uses git log to find modified files under `.planning/phases/`, it needs to parse the output correctly.
**Why it happens:** `git log --name-only` output format includes commit info interspersed with filenames.
**How to avoid:** Use `--pretty=format:""` to suppress commit info, leaving only file paths. Filter for `*-SUMMARY.md` pattern. Deduplicate paths.
**Warning signs:** Duplicate GSD phase entries; missing summary context.

## Code Examples

### diff-scan.py CLI Interface
```python
# Source: CONTEXT.md locked decisions
def main():
    parser = argparse.ArgumentParser(
        description="Produce scoped work order for incremental documentation scan"
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--manifests-dir", required=True,
        help="Path to .mg/docs/reference-manifests/")
    parser.add_argument("--docs-dir", required=True,
        help="Path to docs/auto-doc/")
    parser.add_argument("--since", required=True,
        help="ISO timestamp of last generation")
    parser.add_argument("--gsd-dir", default=None,
        help="Path to .planning/phases/ (optional)")
    parser.add_argument("--output", required=True,
        help="Path to write diff-scope.json")
    args = parser.parse_args()
```

### diff-scope.json Output Structure
```json
{
  "since": "2026-03-17T14:30:00Z",
  "summary": {
    "files_changed": 15,
    "files_added": 3,
    "files_deleted": 1,
    "sections_affected": 8,
    "new_file_candidates": 3
  },
  "affected_sections": [
    {
      "audience": "developers",
      "document": "ARCHITECTURE",
      "section": "system-architecture",
      "reason": "source file modified",
      "changed_files": ["src/llm/model_routing.py"],
      "gsd_context": "Phase 6: replaced route_model() with provider-specific functions",
      "renames": {"src/old/model.py": "src/llm/model_routing.py"}
    }
  ],
  "new_file_candidates": [
    {
      "file": "src/verify/add-verify-finding.py",
      "reason": "new file, not in any manifest",
      "gsd_context": null
    }
  ],
  "deleted_files": [
    {
      "file": "src/old/legacy.py",
      "referenced_in": [
        {"audience": "developers", "document": "ARCHITECTURE", "section": "data-model"}
      ]
    }
  ],
  "gsd_phases_since": [
    {
      "phase": "06",
      "name": "fix-verify-feedback-loop",
      "deviations": [],
      "key_decisions": ["replaced route_model with provider-specific functions"]
    }
  ]
}
```

### Incremental Mode Detection in Scan Command
```
# Added to auto-doc-scan.md Step 12 (Detect mode)
# After existing mode detection, add incremental check:

12b. **Detect incremental mode.** If mode is "update":
    a. Read `.mg/docs/docs-scan.json` and check for `last_generated` field
    b. Check `.mg/docs/reference-manifests/` for at least one manifest file
    c. If BOTH exist: `mode = "incremental"` (upgrade from "update")
    d. If either missing: remain as `mode = "update"` (full scan, same as current)
```

### Scan Agent Incremental Prompt Addition
```
# Additional context passed to scan-audience.md in incremental mode:

Mode: incremental
Only analyze these changed files: ["src/app.py", "src/models.py"]
GSD context for changes:
  Phase 06: replaced route_model() with provider-specific functions

Baseline entries for unchanged sections (copy VERBATIM into your output):
{
  "ARCHITECTURE/data-model": {
    "source_files": ["src/db/models.py"],
    "staleness": "unknown"
  }
}

New file candidates to classify into your document sections:
  - src/verify/add-verify-finding.py (new file, not in any manifest)

For new files: auto-classify into the most appropriate section based on
content and location. Add to source_material_index with "source": "incremental".
```

### Git Rename Parsing
```python
# Verified: git diff -M --diff-filter=R --name-status outputs: R<score>\t<old>\t<new>
def get_renames(base_commit, project_root):
    """Extract file rename pairs between base_commit and HEAD.

    Returns:
        Dict mapping old_path -> new_path for all renames.
    """
    cmd = [
        "git", "diff", "-M", "--diff-filter=R",
        "--name-status", base_commit, "HEAD",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", cwd=project_root,
    )
    if result.returncode != 0:
        return {}
    renames = {}
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            renames[parts[1]] = parts[2]
    return renames
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Full codebase scan every time | Incremental scan scoped by git diff + manifests | Phase 16 | Faster re-scans, focused agent work |
| Staleness check drives scoping | diff-scan.py drives scoping; staleness check is post-generate validation | Phase 16 | Clearer separation of concerns |
| No `last_generated` timestamp | Global `last_generated` in docs-scan.json | Phase 16 | Enables diff baseline resolution |

**Unchanged:**
- `merge-scan.py` works unchanged (receives complete per-audience files regardless of mode)
- `write-scan-output.py` works unchanged (extra fields like `"source"` pass through)
- Verify pipeline runs unchanged (always full, no scoping)
- Generate pipeline unchanged (receives complete docs-scan.json)

## Open Questions

1. **Whether to extend `lib/git_helpers.py` vs keep git logic in `diff-scan.py`**
   - What we know: CONTEXT.md says `staleness-check.py` git helpers are reusable. The existing helpers cover `git_log_since`, `git_file_changed_since`, `git_last_modified` but NOT `git rev-list`, `git diff --name-only`, or `git diff --diff-filter=R`.
   - What's unclear: Whether adding 3 new functions to `git_helpers.py` vs keeping them internal to `diff-scan.py` produces better architecture.
   - Recommendation: Add new functions to `git_helpers.py` -- keeps the "all git operations go through the shared helper" pattern clean. This also makes them independently testable and reusable for future features. This is Claude's discretion per CONTEXT.md.

2. **Whether to add `--dry-run` mode to diff-scan.py**
   - What we know: CONTEXT.md lists this as Claude's discretion.
   - Recommendation: Skip for now. The script's output is a JSON file that can be inspected. A dry-run would just print the same data to stdout, adding complexity without clear value. The scan command already shows a summary after running the script.

3. **How to handle `last_generated` write timing**
   - What we know: CONTEXT.md says "Written by the generate command at pipeline start." The generate command (`auto-doc-generate.md`) currently does not write this field.
   - Recommendation: The generate command should write `last_generated` to `docs-scan.json` at the START of generation (Step 1 or between Step 1 and Step 2). This makes the next diff over-inclusive by design. This is a small modification to the generate command.

4. **Error handling for corrupt manifests**
   - What we know: CONTEXT.md lists this as Claude's discretion.
   - Recommendation: If a manifest file fails to parse (invalid JSON), log a warning and skip that audience's manifest. The affected sections for that audience will be empty (no cross-reference possible), which causes a full scan for that audience's content -- safe, over-inclusive behavior.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (dev dependency in pyproject.toml) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py -x` |
| Full suite command | `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ISC-02 | diff-scan.py produces correct diff-scope.json | unit | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py -x` | Wave 0 |
| ISC-03 | Rename detection produces single entries with old-new mapping | unit | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py::TestRenameDetection -x` | Wave 0 |
| ISC-05 | New files classified as candidates (not in any manifest) | unit | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py::TestNewFileCandidates -x` | Wave 0 |
| ISC-06 | GSD optional -- empty context when no GSD dir | unit | `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py::TestGSDOptional -x` | Wave 0 |
| ISC-01 | Mode detection logic (initial vs incremental) | manual-only | Requires full pipeline run with docs/manifests/docs-scan.json | N/A |
| ISC-04 | Scan agents receive scoped input + carry forward | manual-only | Requires LLM agent execution via Task tool | N/A |
| ISC-07 | Diff-focused summary shown after incremental scan | manual-only | Requires LLM scan command execution | N/A |
| ISC-08 | Verify runs unchanged in both modes | manual-only | Existing verify behavior, no code changes | N/A |
| ISC-09 | Full re-scan by deleting docs + docs-scan.json | manual-only | Requires pipeline state manipulation | N/A |

### Sampling Rate
- **Per task commit:** `python3 -m pytest auto-doc/scripts/tests/test_diff_scan.py -x --tb=short -q --no-header`
- **Per wave merge:** `python3 -m pytest auto-doc/scripts/tests/ -x --tb=short -q --no-header`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `auto-doc/scripts/tests/test_diff_scan.py` -- covers ISC-02, ISC-03, ISC-05, ISC-06
- No framework install needed (pytest already in dev dependencies)
- No conftest.py needed (existing tests don't use one; each test file is self-contained)

## Sources

### Primary (HIGH confidence)
- Existing codebase: `auto-doc/scripts/lib/git_helpers.py` -- current git helper patterns
- Existing codebase: `auto-doc/scripts/staleness-check.py` -- git subprocess patterns, docs-meta parsing
- Existing codebase: `auto-doc/scripts/merge-scan.py` -- merge behavior and scan-logs consumption
- Existing codebase: `auto-doc/references/schema.md` -- manifest structure, docs-scan.json contract
- Existing codebase: `auto-doc/commands/auto-doc-scan.md` -- current scan pipeline flow
- Existing codebase: `auto-doc/agents/scan-audience.md` -- current scan agent contract
- CONTEXT.md (16-CONTEXT.md) -- all locked decisions and design specification
- Source document: `docs/work-queue/auto-doc-1.1/phase-5-incremental-scan.md` -- original design

### Secondary (MEDIUM confidence)
- Git documentation: `git diff -M` rename detection format verified via local test (R100\told\tnew)
- Git documentation: `git rev-list --before` behavior verified via local test

### Tertiary (LOW confidence)
None -- all findings verified against codebase and git behavior.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, all patterns established in existing codebase
- Architecture: HIGH -- extends existing scan pipeline with one new script and prompt modifications
- Pitfalls: HIGH -- identified from direct codebase analysis (merge-scan.py scan-logs glob, timestamp edge cases)

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable -- internal tooling, no external API dependencies)
