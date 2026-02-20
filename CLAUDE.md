# CLAUDE.md

## Project Overview

`mg-cc-tools` is a collection of Claude Code commands and tools under the `mg:` namespace. Each tool lives in its own subdirectory with an install script.

## Structure

```
mg-cc-tools/
├── codebase-health/     ← 3-step codebase health pipeline
│   ├── install.sh       ← per-tool installer
│   ├── README.md        ← tool-specific docs
│   ├── commands/        ← Claude Code command files (.md)
│   ├── agents/          ← scanner subagent instructions
│   └── references/      ← shared schema
└── (future tools)
```

## Conventions

- Each tool gets its own subdirectory
- Each tool has an `install.sh` that deploys to `.claude/commands/mg/` and `.claude/<tool-name>/`
- Command files use the `mg:` namespace prefix
- Install scripts resolve relative paths to absolute at install time
- Tools should work independently — no cross-tool dependencies

## Git Workflow

- Work on feature branches, merge via PR
- Keep commits atomic with clear messages
