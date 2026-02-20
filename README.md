# mg-cc-tools

A collection of Claude Code commands and tools under the `mg:` namespace.

## Tools

| Tool | Description | GSD Required | Install |
|---|---|---|---|
| [codebase-health](codebase-health/) | 3-step pipeline for auditing and cleaning codebases (scan, verify, implement) | No | `codebase-health/install.sh --project` |
| [debug-triage](debug-triage/) | Maps full data flow for a bug, identifies all break points, routes to debug or phase | Yes | `debug-triage/install.sh --project` |
| [update-backlog](update-backlog/) | Scans `.planning/` for deferred items, deduplicates, syncs to `BACKLOG.md` | Yes | `update-backlog/install.sh --project` |
| [new-milestone-gsd](new-milestone-gsd/) | Gate for `/gsd:new-milestone` — shows backlog status, offers update first | Yes | `new-milestone-gsd/install.sh --project` |

## Installation

Each tool has its own `install.sh` that handles setup. Run it from your project root:

```bash
cd /path/to/your/project
/path/to/mg-cc-tools/codebase-health/install.sh --project
/path/to/mg-cc-tools/debug-triage/install.sh --project
/path/to/mg-cc-tools/update-backlog/install.sh --project
/path/to/mg-cc-tools/new-milestone-gsd/install.sh --project
```

Or install globally (available in all projects):

```bash
/path/to/mg-cc-tools/codebase-health/install.sh --global
```

The GSD-dependent tools (`debug-triage`, `update-backlog`, `new-milestone-gsd`) require [Get Shit Done](https://github.com/getsdo/gsd) to be installed. They enhance the GSD SDLC workflow with bug triage, backlog management, and milestone gating.

See each tool's README for detailed usage.

## Namespace

All commands use the `/mg:` prefix (e.g., `/mg:codebase-health`).
