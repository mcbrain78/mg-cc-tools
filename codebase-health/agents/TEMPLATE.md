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
- **output_json_path**: Where to write the findings JSON array.
- **output_log_path**: Where to write the human-readable log.

## Process

1. **Read orientation** — Understand the project's structure, languages, entry points.
2. **Search systematically** — Use grep, file listing, and file reading to find instances matching your category's detection criteria (see the relevant category section in SKILL.md).
3. **Evaluate each candidate** — Assess severity and confidence. Check for false positive conditions.
4. **Write findings JSON** — Array of finding objects (see format below).
5. **Write scan log** — Markdown summary of what you checked and what you found.

## Finding Format

Each finding in the JSON array:

```json
{
  "category": "[category-slug]",
  "severity": "critical | high | medium | low",
  "confidence": "high | medium | low",
  "title": "Short description of the finding",
  "location": {
    "file": "relative/path/to/file",
    "lines": [10, 25],
    "symbol": "function_or_class_name_or_null"
  },
  "evidence": "Specific explanation of what was observed and why it's a finding.",
  "recommendation": "remove | refactor | update | merge | investigate",
  "notes": "Caveats, uncertainty, or additional context. Empty string if none."
}
```

## Principles

- Never modify project files.
- Prefer false negatives over false positives.
- Always check for dynamic dispatch / reflection before flagging orphaned or dead code.
- Be specific: file paths, line numbers, symbol names.
- Cite evidence: what you saw, not just what you concluded.
