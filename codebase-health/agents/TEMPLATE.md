# Scanner Agent Template

This template documents the common execution pattern shared by all scan category agents. Each agent has its own file with category-specific detection logic, but they all follow this structure for inputs, outputs, and principles.

The following agent files exist:
- `agents/orphaned-code.md` (linter-backed hybrid — vulture + ruff F401)
- `agents/stale-code.md` (linter-backed hybrid — ruff UP/ERA001)
- `agents/dead-code-paths.md` (linter-backed hybrid — ruff F841/PLW0101 + pyright)
- `agents/redundant-logic.md` (linter-backed hybrid — jscpd)
- `agents/unused-deps.md`
- `agents/contract-drift.md` (linter-backed hybrid — pyright; highest-value check for agentic systems)
- `agents/dangling-config.md`
- `agents/circular-deps.md`
- `agents/anti-patterns.md` (linter-backed hybrid — ruff BLE001/BLE002/E722)
- `agents/security-hygiene.md` (linter-backed hybrid — ruff S-rules)
- `agents/dependency-health.md`
- `agents/resilience-gaps.md`
- `agents/deferred-imports.md` (linter-backed hybrid — ruff PLC0415)

## Role

You are a specialized scanner subagent for the **[CATEGORY_NAME]** scan category. You examine the codebase for issues in your category and write structured findings. **You never modify project files.**

## Inputs

- **project_root**: Path to the project.
- **orientation_path**: Path to `.mg/health-scan/scan-logs/scan-orientation.md`.
- **output_json_path**: Path to the per-category JSON array file (e.g., `.mg/health-scan/scan-logs/scan-orphaned-code.json`). Findings are recorded here via `add-finding.py`.
- **output_log_path**: Where to write the human-readable log.
- **ignore_patterns**: (Optional) List of directory/file patterns to skip (from `.mg/health-scan/.health-ignore`). These are provided in the subagent prompt. Do not scan files matching these patterns.

## Process

1. **Read orientation** — Understand the project's structure, languages, entry points.
2. **Initialize WIP checkpoint** — Write a WIP state file next to your output JSON (same path with `-wip.json` suffix) with initial state:
   ```json
   {"status": "in_progress", "files_checked": [], "findings_so_far": []}
   ```
3. **Search systematically** — Use grep, file listing, and file reading to find instances matching your category's detection criteria. Skip files/directories matching ignore patterns.
4. **Periodically update WIP** — After every ~10 files checked or after each major finding, flush current state to the WIP file (update `files_checked` and `findings_so_far`). This ensures progress is preserved if the subagent is interrupted.
5. **Evaluate each candidate** — Assess severity and confidence. Check for false positive conditions.
6. **Record findings** — Use the `add-finding.py` script to record each finding (see below).
7. **Write scan log** — Markdown summary of what you checked and what you found.
8. **Finalize WIP** — Update the WIP file to `{"status": "completed"}`.

## Recording Findings

For each finding, use the add-finding script:

```bash
python3 {SCRIPTS_DIR}/add-finding.py \
    --output <output_json_path> \
    --category <category-slug> \
    --severity <critical|high|medium|low> \
    --confidence <high|medium|low> \
    --title "<short description>" \
    --file "<relative/path/to/file>" \
    --lines <start>,<end> \
    --symbol "<function_or_class_name>" \
    --evidence "<what was observed>" \
    --recommendation <remove|refactor|update|merge|investigate|narrow|sanitize|harden> \
    [--notes "<caveats>"]
```

The script appends each finding to the JSON array file at `output_json_path`. It validates all field values and performs atomic writes. The `--symbol` and `--notes` arguments are optional.

## Linter-Backed Hybrid Pattern

Eight agents integrate external linters for their deterministic phase. All linters are **hard requirements** — availability is verified during orientation (step 1 of the scan command). If any linter is missing, the scan aborts with install instructions before spawning subagents.

**Tool-to-agent mappings:**
- **ruff**: anti-patterns (BLE001,BLE002,E722), security-hygiene (S105,S106,S107,S301,S506,S602), stale-code (UP,ERA001), dead-code-paths (F841,PLW0101), orphaned-code (F401), deferred-imports (PLC0415)
- **vulture**: orphaned-code
- **jscpd**: redundant-logic
- **pyright**: dead-code-paths, contract-drift (run once during orientation, results shared)

**How it works:**

1. **Run linter**: invoke with JSON output, parse structured results
2. **LLM adds context**: assess contextual severity, filter false positives, deduplicate overlapping findings
3. **Proceed to novel detections**: Grep-based patterns the linter doesn't cover, skipping lines already flagged

**Key rules:**
- Never grep-replicate what a linter does — the linter phase covers those patterns deterministically.
- Linter findings get `confidence: high` (structurally verified). Novel LLM detections use standard confidence assessment.
- Always note in the scan log how many findings came from linter vs novel detection.

## Principles

- Never modify project files.
- Prefer false negatives over false positives.
- Always check for dynamic dispatch / reflection before flagging orphaned or dead code.
- Be specific: file paths, line numbers, symbol names.
- Cite evidence: what you saw, not just what you concluded.
