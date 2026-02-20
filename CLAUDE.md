# CLAUDE.md

## Project Overview

`mg-cc-tools` is a collection of Claude Code commands and tools under the `mg:` namespace. Each tool lives in its own subdirectory with an install script.

## Structure

```
mg-cc-tools/
├── codebase-health/         ← 3-step codebase health pipeline
│   ├── install.sh           ← per-tool installer
│   ├── README.md            ← tool-specific docs
│   ├── commands/            ← Claude Code command files (.md)
│   ├── agents/              ← scanner subagent instructions
│   ├── scripts/             ← Python helper scripts
│   └── references/          ← shared schema
├── debug-triage/            ← bug triage & data flow mapping (GSD extension)
│   ├── install.sh
│   └── commands/
├── update-backlog/          ← .planning/ backlog scanner (GSD extension)
│   ├── install.sh
│   └── commands/
└── new-milestone-gsd/       ← milestone gate with backlog check (GSD extension)
    ├── install.sh
    └── commands/
```

## Conventions

- Each tool gets its own subdirectory
- Each tool has an `install.sh` that deploys to `.claude/commands/mg/` and `.claude/<tool-name>/` (if needed)
- Command files use the `mg:` namespace prefix
- Install scripts resolve relative paths to absolute at install time
- Tools should work independently — no cross-tool dependencies
- GSD-dependent tools require Get Shit Done to be installed in the target project

## Git Workflow

- Work on feature branches, merge via PR
- Keep commits atomic with clear messages
