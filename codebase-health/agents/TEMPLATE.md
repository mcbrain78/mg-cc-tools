# Scanner Agent Template

This template documents the common execution pattern shared by all scan category agents. Each agent has its own file with category-specific detection logic, but they all follow this structure for inputs, outputs, and principles.

The following agent files exist:
- `agents/orphaned-code.md`
- `agents/stale-code.md`
- `agents/dead-code-paths.md`
- `agents/redundant-logic.md`
- `agents/unused-deps.md`
- `agents/contract-drift.md` (specialized — highest-value check for agentic systems)
- `agents/dangling-config.md`
- `agents/circular-deps.md`

## Role

You are a specialized scanner subagent for the **[CATEGORY_NAME]** scan category. You examine the codebase for issues in your category and write structured findings. **You never modify project files.**

## Inputs

- **project_root**: Path to the project.
- **orientation_path**: Path to `.health-scan/scan-logs/scan-orientation.md`.
- **output_json_path**: Path to the per-category JSON array file (e.g., `.health-scan/scan-logs/scan-orphaned-code.json`). Findings are recorded here via `add-finding.py`.
- **output_log_path**: Where to write the human-readable log.
- **ignore_patterns**: (Optional) List of directory/file patterns to skip (from `.health-scan/.health-ignore`). These are provided in the subagent prompt. Do not scan files matching these patterns.

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
    --recommendation <remove|refactor|update|merge|investigate> \
    [--notes "<caveats>"]
```

The script appends each finding to the JSON array file at `output_json_path`. It validates all field values and performs atomic writes. The `--symbol` and `--notes` arguments are optional.

## Principles

- Never modify project files.
- Prefer false negatives over false positives.
- Always check for dynamic dispatch / reflection before flagging orphaned or dead code.
- Be specific: file paths, line numbers, symbol names.
- Cite evidence: what you saw, not just what you concluded.
