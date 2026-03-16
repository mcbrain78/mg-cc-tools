# Phase 3: Scan Pipeline - Research

**Researched:** 2026-03-16
**Domain:** LLM command orchestration, scan pipeline design, Claude Code Task tool delegation
**Confidence:** HIGH

## Summary

Phase 3 builds the `/mg:create-docs-scan` command -- the read-only analysis step that produces `docs-scan.json` for downstream generation. The command must orchestrate several analysis concerns: project orientation (tech stack, components, entry points), source material indexing (mapping code files to document sections), staleness detection (code-reference and git-freshness checks), GSD context loading, notes inbox classification, and gap analysis. All results merge into a single JSON contract via the existing `merge-scan.py` script.

The implementation follows the well-established codebase-health scan pattern already in this repository: the command reads orientation data, spawns per-audience subagents via the Task tool, each subagent writes partial results to `.mg/docs/scan-logs/`, and a Python merge script produces the final output. All supporting infrastructure (scripts, schema, agents, lib modules) was built and verified in Phases 1-2. The primary work is writing the scan command's LLM instruction prompt and potentially audience-specific scan agent definitions.

**Primary recommendation:** Build the scan command as a single large command .md file following the codebase-health-scan.md pattern. Orientation runs inline, then per-audience scan subagents are spawned in parallel via Task tool. Subagents receive project orientation context plus their audience scope. Final merge uses existing `merge-scan.py`. No new Python scripts are needed -- all infrastructure exists.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Project Orientation (SCN-01)**: Build understanding of code structure, tech stack, frameworks, entry points. Scan deployment artifacts, existing docs, database schemas, API contracts, config files, environment files.
- **Source Material Index (SCN-02)**: Map code files to document sections. Index structure: `documents -> {doc_path} -> sections -> {section_name} -> sources[] + staleness`. Each source entry is a file path with staleness marker (null on initial scan).
- **GSD Context Loading (SCN-03)**: If `.planning/` exists, read SUMMARY.md files, REQUIREMENTS.md traceability, VERIFICATION.md gaps, MILESTONES.md.
- **Staleness Detection -- Code References (SCN-04)**: Uses `check-references.py` built in Phase 1.
- **Staleness Detection -- Git Freshness (SCN-05)**: Uses `staleness-check.py` built in Phase 1.
- **Notes Inbox Classification (SCN-06)**: Classify pending notes with audience, document, section, confidence. Produces proposed expansion outline per note.
- **Gap Analysis (SCN-07)**: Identify undocumented components per audience. Output: `undocumented_components[]` and `missing_for_audience` per audience.
- **Scan Output (SCN-08)**: Output to `.mg/docs/docs-scan.json` matching schema.
- **Scan Command (CMD-02)**: Command `/mg:create-docs-scan`, read-only, spawns per-audience scan subagents merging via `merge-scan.py`.
- **Cross-Cutting**: Scan agents receive file paths only, read files themselves. Tool installs to `.claude/create-docs/`. Road-runner validation baked into success criteria.

### Claude's Discretion
- Scan agent orchestration pattern (sequential vs parallel per audience)
- How orientation results are structured before being fed to source material indexing
- Staleness severity thresholds and categorization
- How scan-logs/ files are structured (scan-orientation.md, scan-end-users.md, etc.)
- Schema drift and terminology drift detection approach (v2 features, basic versions may emerge)

### Deferred Ideas (OUT OF SCOPE)
- Schema drift detection (STL-01) -- v2
- Terminology drift detection (STL-02) -- v2
- GSD deviation signals (STL-03) -- v2 (basic version may emerge naturally)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCN-01 | Project orientation: code structure, tech stack, entry points, deployment artifacts, existing docs | Codebase-health-scan.md Step 1 (Orient) pattern. Inline in command, writes scan-orientation.md to scan-logs/. |
| SCN-02 | Source material index mapping code files to document sections | Per-audience subagents build partial indexes. merge-scan.py merges via `merge_source_material()`. Schema defines `source_material_index` format. |
| SCN-03 | GSD context loading: phase SUMMARYs, REQUIREMENTS.md traceability, VERIFICATION.md gaps | Inline in command after orientation. Reads `.planning/` directory. Writes `gsd_context` object for merge. |
| SCN-04 | Staleness detection: code-reference checks | `check-references.py` exists (365 lines, 16 tests). Used by staleness-scanner agent. Accepts `--docs-dir` and `--project-root`. |
| SCN-05 | Staleness detection: git-based section freshness | `staleness-check.py` exists (302 lines, 14 tests). Parses docs-meta HTML comments, uses `lib/git_helpers.py`. Accepts `--docs-dir` and `--project-root`. |
| SCN-06 | Notes inbox classification | `classify-note.py` exists (161 lines, 11 tests). Command iterates pending notes and classifies each. |
| SCN-07 | Gap analysis: undocumented components per audience | Per-audience subagents identify gaps for their audience. merge-scan.py merges via `merge_gap_analysis()` (sorted union). |
| SCN-08 | Output as docs-scan.json shared data contract | `merge-scan.py` produces final JSON (230 lines, 10 tests). Schema in `references/schema.md` defines all 9 top-level fields. |
| CMD-02 | `/mg:create-docs-scan` analyzes project and builds source material index | Command stub exists with frontmatter. Phase 3 overwrites with full LLM instruction prompt. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Claude Code Task tool | built-in | Spawn per-audience scan subagents | Established pattern in codebase-health-scan.md; isolates context per audience |
| merge-scan.py | Phase 1 | Merge per-audience scan JSON into docs-scan.json | Already built and tested (10 tests); handles deduplication, severity ranking |
| check-references.py | Phase 1 | Verify file paths and symbols exist | Already built and tested (16 tests); used by staleness-scanner agent |
| staleness-check.py | Phase 1 | Git-based section freshness analysis | Already built and tested (14 tests); parses docs-meta comments |
| classify-note.py | Phase 1 | Classify notes by audience/document/section | Already built and tested (11 tests); keyword heuristics |
| lib/json_io.py | Phase 1 | Atomic JSON load/save | Already built; used by all scripts |
| lib/git_helpers.py | Phase 1 | Git subprocess wrappers | Already built; used by staleness-check.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Bash tool | built-in | Run Python scripts, directory listings | Script invocation, workspace validation |
| Read tool | built-in | Read source files, config, existing docs | Orientation step, agent source reading |
| Glob tool | built-in | File pattern matching | Discovering project structure, doc files |
| Grep tool | built-in | Content search | Tech stack detection, entry point detection |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-audience subagents | Single monolithic scan | Monolithic would hit context limits on large projects; per-audience mirrors codebase-health proven pattern |
| Task tool subagents | Sequential inline scan | Sequential works but is slower; Task tool enables parallelism for 4 audiences |
| classify-note.py (deterministic) | LLM classification | Deterministic is faster, reproducible; LLM adds nuance but is slower and non-deterministic |

## Architecture Patterns

### Recommended Project Structure (scan command deliverables)
```
create-docs/
├── commands/
│   └── create-docs-scan.md    <- PRIMARY DELIVERABLE: full scan orchestration prompt
├── agents/
│   ├── scan-audience.md       <- NEW: per-audience scan subagent template (Claude's discretion)
│   └── staleness-scanner.md   <- EXISTS: unchanged
├── scripts/
│   ├── merge-scan.py          <- EXISTS: unchanged
│   ├── check-references.py    <- EXISTS: unchanged
│   ├── staleness-check.py     <- EXISTS: unchanged
│   └── classify-note.py       <- EXISTS: unchanged
└── references/
    └── schema.md              <- EXISTS: data contract
```

### Pattern 1: Scan Orchestration (from codebase-health-scan.md)

**What:** The command file is an LLM instruction prompt that orchestrates a multi-step pipeline: orient, scan categories in parallel via Task tool, merge results.

**When to use:** Always -- this is the established pattern for complex scan commands in mg-cc-tools.

**Example (adapted from codebase-health-scan.md):**
```markdown
### Step 1: Orient
1. Identify the project root directory.
2. Read top-level structure (2-3 levels deep).
3. Identify languages, frameworks, package managers.
4. Identify entry points.
5. Load config from .mg/docs/.docs.config.json.
6. Detect mode: "initial" (no existing docs) or "update" (existing docs found).
7. Write scan-orientation.md to .mg/docs/scan-logs/.

### Step 2: GSD Context (conditional)
If .planning/ exists and gsd_integration is true:
1. Read MILESTONES.md, STATE.md
2. Read all SUMMARY.md files from completed phases
3. Read REQUIREMENTS.md traceability table
4. Read VERIFICATION.md files for gaps
5. Write gsd-context.json to scan-logs/

### Step 3: Staleness Check (update mode only)
If mode is "update" and existing docs directory exists:
1. Run staleness-check.py --docs-dir <docs_dir> --project-root <project_root>
2. Run check-references.py --docs-dir <docs_dir> --project-root <project_root>
3. Write combined results to scan-logs/

### Step 4: Notes Classification
If notes-inbox.json has pending notes:
1. For each pending note, run classify-note.py
2. Collect classifications

### Step 5: Per-Audience Scan (parallel via Task tool)
For each enabled audience in config:
1. Spawn a scan subagent via Task tool
2. Subagent receives: orientation summary, audience scope, config, project root
3. Subagent produces: source_material_index, gap_analysis for its audience
4. Subagent writes partial JSON to scan-logs/scan-{audience}.json

### Step 6: Merge
1. Run merge-scan.py to combine all partial results
2. Present summary to user
```

### Pattern 2: Subagent Delegation (from codebase-health-scan.md)

**What:** Each subagent is spawned via the Task tool with a composed prompt that includes the agent instructions (read from the agent file and pasted into the prompt), orientation context, and output paths.

**When to use:** For per-audience scan work that benefits from context isolation.

**Key detail from codebase-health:** The orchestrator reads agent .md files and pastes their contents into the Task tool prompt. Subagents cannot read paths relative to the command file -- the orchestrator must provide absolute paths.

```
Task(
  description="Scan source material for developers audience",
  prompt="You are a scan subagent for the developers audience. [agent instructions]\n\n
    Project root: /path/to/project\n
    Read orientation: /path/.mg/docs/scan-logs/scan-orientation.md\n
    Write output: /path/.mg/docs/scan-logs/scan-developers.json\n
    Your audience: developers\n
    Your documents: ARCHITECTURE, DEVELOPER_GUIDE, QUICK_REFERENCE\n
    ..."
)
```

### Pattern 3: Mode Detection (initial vs update)

**What:** The scan command detects whether this is an initial scan (no existing docs) or an update scan (docs directory exists). This affects which steps run.

**When to use:** Always -- determines whether staleness checks run.

**Logic:**
- Check if `docs_dir` (from config, default `docs/auto-doc`) contains any `.md` files
- If yes: `mode = "update"` -- run staleness checks, reference checks, build on prior scan
- If no: `mode = "initial"` -- skip staleness, produce fresh index

### Anti-Patterns to Avoid

- **Scanning everything inline in one command without subagents.** Large projects will overwhelm context. Use Task tool delegation.
- **Having subagents call merge-scan.py.** Only the orchestrator calls merge after all subagents complete.
- **Passing full file contents to subagents.** Pass file paths only (locked decision). Subagents read files themselves.
- **Modifying any project source files.** Scan is read-only. Only writes to `.mg/docs/` workspace.
- **Not clearing scan-logs/ on re-scan.** Stale partial results from previous runs would corrupt the merge. Clear scan-logs/ at start (except preserve inbox and config).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON merging and deduplication | Custom merge logic in the command | `merge-scan.py` | Already handles source material dedup, staleness severity ranking, gap analysis union, note concatenation |
| Git-based freshness checking | Inline git commands in the command | `staleness-check.py` + `lib/git_helpers.py` | Handles docs-meta parsing, broken references, severity assignment; 14 tests |
| File path and symbol verification | Manual path checking | `check-references.py` | Handles backtick extraction, code block parsing, symbol regex detection; 16 tests |
| Note classification | Inline LLM classification | `classify-note.py` | Deterministic, reproducible keyword heuristics; 11 tests |
| Atomic JSON I/O | Direct file writes | `lib/json_io.py` | Temp file + os.replace prevents corruption |

**Key insight:** Phase 1 built all the deterministic tooling. Phase 3's job is writing the LLM orchestration layer that calls these tools in the right order and delegates audience-specific analysis to subagents.

## Common Pitfalls

### Pitfall 1: CLI Interface Mismatch in Staleness Scanner Agent
**What goes wrong:** The staleness-scanner.md agent references `--doc-file` in its example commands, but the actual scripts (`check-references.py` and `staleness-check.py`) use `--docs-dir`. This could cause runtime errors if the agent follows its own instructions literally.
**Why it happens:** The agent was authored in Phase 2 based on the expected API; the actual scripts use directory-level iteration.
**How to avoid:** The scan command should invoke the scripts directly with `--docs-dir` rather than delegating per-file invocation to the staleness-scanner agent. Or, the scan command should provide explicit instructions that override the agent's `--doc-file` examples with the correct `--docs-dir` flags.
**Warning signs:** Script errors about unknown argument `--doc-file`.

### Pitfall 2: Source Material Index Key Format
**What goes wrong:** The schema defines source_material_index keys as `"DOCUMENT/section"` (e.g., `"ARCHITECTURE/overview"`). If subagents produce keys in a different format (e.g., `"developers/ARCHITECTURE/overview"` or `"architecture/overview"`), the merge script still works (no key validation) but downstream generation will fail to match.
**Why it happens:** No enforcement of key format in merge-scan.py or schema beyond examples.
**How to avoid:** The scan command and agent instructions must specify the exact key format: `{DOCUMENT_NAME}/{section_slug}` where DOCUMENT_NAME matches config entries and section_slug is the template heading slug.
**Warning signs:** Empty source material lookups in generation step.

### Pitfall 3: merge-scan.py Takes project_model from First File Only
**What goes wrong:** The merge script takes `project_model` from the first JSON file that has it (`if project_model is None and "project_model" in data`). If no per-audience file includes project_model, the merged output has `null` for this required field.
**Why it happens:** Project model is a project-wide concern, not per-audience. Per-audience subagents focus on source material and gaps.
**How to avoid:** The scan command must ensure project_model and gsd_context are written to a separate JSON file (e.g., `scan-logs/scan-project.json`) that merge-scan.py picks up. This is the "orientation" output.
**Warning signs:** `"project_model": null` in docs-scan.json.

### Pitfall 4: Update Mode Without Existing Scan Data
**What goes wrong:** On update mode, the command tries to reuse prior scan data, but the previous `docs-scan.json` may have been deleted or moved.
**Why it happens:** User manually deletes `.mg/docs/docs-scan.json` between runs.
**How to avoid:** If mode is "update" but no prior `docs-scan.json` exists, fall back to "initial" mode gracefully.
**Warning signs:** FileNotFoundError when trying to load prior scan data.

### Pitfall 5: GSD Context Loading on Non-GSD Projects
**What goes wrong:** The scan command tries to load `.planning/` data on a project without GSD installed.
**Why it happens:** Config has `gsd_integration: true` by default.
**How to avoid:** Check for `.planning/` directory existence AND `gsd_integration` config flag. If directory does not exist, skip GSD loading and set `gsd_context: null`.
**Warning signs:** Errors about missing `.planning/MILESTONES.md` or similar.

### Pitfall 6: Scan-Logs Directory Not Cleared Between Runs
**What goes wrong:** Stale JSON files from a previous scan in `scan-logs/` get merged into the new scan output.
**Why it happens:** merge-scan.py reads ALL `*.json` in scan-dir (no prefix filter, per Phase 1 decision).
**How to avoid:** Clear `.mg/docs/scan-logs/*.json` at the start of each scan run. Preserve `notes-inbox.json` (which is in the parent directory, not scan-logs).
**Warning signs:** Duplicate or contradictory entries in merged output.

## Code Examples

### merge-scan.py Invocation
```bash
# Source: create-docs/scripts/merge-scan.py --help
python3 {SCRIPTS_DIR}/merge-scan.py \
    --scan-dir <project>/.mg/docs/scan-logs \
    --output <project>/.mg/docs/docs-scan.json \
    --project-name "my-project" \
    --root-path "/absolute/path/to/project" \
    --mode initial
```

### staleness-check.py Invocation
```bash
# Source: create-docs/scripts/staleness-check.py --help
python3 {SCRIPTS_DIR}/staleness-check.py \
    --docs-dir <project>/docs/auto-doc \
    --project-root <project> \
    --output <project>/.mg/docs/scan-logs/staleness-results.json
```

### check-references.py Invocation
```bash
# Source: create-docs/scripts/check-references.py --help
python3 {SCRIPTS_DIR}/check-references.py \
    --docs-dir <project>/docs/auto-doc \
    --project-root <project> \
    --output <project>/.mg/docs/scan-logs/refs-check.json
```

### classify-note.py Invocation
```bash
# Source: create-docs/scripts/classify-note.py --help
python3 {SCRIPTS_DIR}/classify-note.py \
    --text "Deploy the server with new config" \
    --note-id NOTE-001 \
    --inbox <project>/.mg/docs/notes-inbox.json
```

### Per-Audience Scan Subagent Output Format
```json
{
  "source_material_index": {
    "ARCHITECTURE/overview": {
      "source_files": ["src/app.ts", "src/routes/index.ts"],
      "staleness": "unknown"
    },
    "DEVELOPER_GUIDE/getting-started": {
      "source_files": ["package.json", "README.md"],
      "staleness": "unknown"
    }
  },
  "gap_analysis": {
    "undocumented_components": ["src/utils/crypto.ts"],
    "missing_for_audience": {
      "developers": ["api-reference", "testing-strategy"]
    }
  }
}
```

### Orientation Output (scan-project.json for merge)
```json
{
  "project_model": {
    "tech_stack": ["python", "bash", "markdown"],
    "entry_points": [
      {"path": "scripts/add-note.py", "type": "cli", "description": "Atomic append to notes inbox"}
    ],
    "components": [
      {"name": "json_io", "path": "scripts/lib/json_io.py", "purpose": "Atomic JSON helpers", "public_api": ["load_json", "save_json"], "dependencies": ["json", "os"], "database_tables": []}
    ],
    "infrastructure": {"deployment": "bash install script", "ci": "none", "config_files": ["pyproject.toml"]}
  },
  "gsd_context": null
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single monolithic scan agent | Per-audience parallel subagents via Task tool | codebase-health v1 | Prevents context window overflow; enables audience-specific analysis |
| Per-file script invocation | Directory-level script invocation | Phase 1 implementation | Scripts iterate directories internally; command invokes once per operation |
| LLM-based note classification | Deterministic keyword heuristics | Phase 1 decision 01-02 | Faster, reproducible, testable |

**Important existing tool interface notes:**
- `check-references.py`: takes `--docs-dir` (directory), NOT `--doc-file` (per-file)
- `staleness-check.py`: takes `--docs-dir` (directory), NOT `--doc-file` (per-file)
- `merge-scan.py`: reads ALL `*.json` in `--scan-dir` (no filename prefix filter)
- `classify-note.py`: classifies one note at a time via `--text`

## Open Questions

1. **Scan subagent granularity: one generic agent template or four audience-specific agents?**
   - What we know: Codebase-health uses per-category agent .md files (14 of them). The docs pipeline has 4 audiences with very different source material concerns.
   - What's unclear: Whether a single `scan-audience.md` template with audience parameter is sufficient, or if each audience needs a specialized scan agent (e.g., agent audience scans differently from end-user audience).
   - Recommendation: Start with a single generic scan-audience agent template. The per-audience specialization comes from the documents list and templates, not from different scanning strategies. If needed, specialize later.

2. **Orientation output format and persistence**
   - What we know: Codebase-health writes `scan-orientation.md` as markdown. The docs pipeline needs the orientation as both human-readable (scan-logs) and machine-readable (project_model for merge).
   - What's unclear: Whether to write one file (markdown) or two (markdown + JSON).
   - Recommendation: Write both `scan-orientation.md` (human-readable log) and `scan-project.json` (structured data for merge-scan.py to pick up for project_model and gsd_context). The JSON file participates in the merge.

3. **How staleness and reference checks integrate with per-audience scan**
   - What we know: Staleness checks operate on the docs directory as a whole. Per-audience scans operate on audience-specific document lists.
   - What's unclear: Whether staleness/reference checks run before per-audience scans (as a centralized step) or within each audience scan.
   - Recommendation: Run staleness and reference checks centrally (before per-audience scans) and write results to scan-logs. Per-audience subagents reference these results when building their source_material_index staleness markers. This avoids running the scripts 4 times.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml |
| Quick run command | `python3 -m pytest create-docs/scripts/tests/ -x -q` |
| Full suite command | `python3 -m pytest -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCN-01 | Project orientation populates project_model | manual-only | N/A -- LLM analysis, not script | N/A |
| SCN-02 | Source material index maps code to doc sections | manual-only | N/A -- LLM analysis, not script | N/A |
| SCN-03 | GSD context loads planning data | manual-only | N/A -- LLM reads .planning/ | N/A |
| SCN-04 | Staleness detection via code references | unit | `python3 -m pytest create-docs/scripts/tests/test_check_references.py -x` | Yes (16 tests) |
| SCN-05 | Staleness detection via git freshness | unit | `python3 -m pytest create-docs/scripts/tests/test_staleness_check.py -x` | Yes (14 tests) |
| SCN-06 | Notes inbox classification | unit | `python3 -m pytest create-docs/scripts/tests/test_classify_note.py -x` | Yes (11 tests) |
| SCN-07 | Gap analysis per audience | manual-only | N/A -- LLM analysis, not script | N/A |
| SCN-08 | Output as valid docs-scan.json | unit | `python3 -m pytest create-docs/scripts/tests/test_merge_scan.py -x` | Yes (10 tests) |
| CMD-02 | create-docs-scan command produces scan output | smoke | Run `/mg:create-docs-scan` on road-runner project | No -- manual |

### Sampling Rate
- **Per task commit:** `python3 -m pytest create-docs/scripts/tests/ -x -q`
- **Per wave merge:** `python3 -m pytest -x -q`
- **Phase gate:** Full suite green + manual smoke test on road-runner before `/gsd:verify-work`

### Wave 0 Gaps
None -- existing test infrastructure covers all scriptable phase requirements. SCN-01/02/03/07 are LLM analysis concerns that cannot be unit-tested; they are verified by the road-runner smoke test in the success criteria.

## Sources

### Primary (HIGH confidence)
- `codebase-health/commands/codebase-health-scan.md` -- Reference implementation for scan orchestration, subagent delegation, orientation pattern, merge pattern. Read directly from repository.
- `create-docs/references/schema.md` -- Complete data contract for docs-scan.json. Read directly from repository.
- `create-docs/scripts/merge-scan.py` -- Merge logic, CLI interface, deduplication rules. Read directly from repository.
- `create-docs/scripts/staleness-check.py` -- Freshness analysis, docs-meta parsing, CLI interface. Read directly from repository.
- `create-docs/scripts/check-references.py` -- Reference checking, CLI interface. Read directly from repository.
- `create-docs/scripts/classify-note.py` -- Note classification, CLI interface. Read directly from repository.
- `create-docs/agents/staleness-scanner.md` -- Agent instructions, CLI mismatch identified. Read directly from repository.
- `create-docs/agents/TEMPLATE.md` -- Writer agent pattern, execution order. Read directly from repository.
- `create-docs/install.sh` -- Install structure, sed resolution, agent copying. Read directly from repository.
- `.planning/phases/01-foundation-infrastructure/01-VERIFICATION.md` -- Phase 1 complete, all 59 tests passing. Read directly from repository.
- `.planning/phases/02-templates-agent-definitions/02-VERIFICATION.md` -- Phase 2 complete, all artifacts verified. Read directly from repository.

### Secondary (MEDIUM confidence)
- None needed -- all research sourced from repository code.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all tools exist in repo, verified in Phase 1/2
- Architecture: HIGH - follows proven codebase-health pattern in same repo
- Pitfalls: HIGH - identified from actual code reading (CLI mismatch, merge behavior)

**Research date:** 2026-03-16
**Valid until:** Indefinite (all sources are internal to the repository)
