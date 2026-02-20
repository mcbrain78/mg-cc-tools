# mg-cc-tools

A collection of Claude Code commands and tools under the `mg:` namespace.

## Tools

| Tool | Description | Install |
|---|---|---|
| [codebase-health](codebase-health/) | 3-step pipeline for auditing and cleaning codebases (scan, verify, implement) | `codebase-health/install.sh --project` |

## Installation

Each tool has its own `install.sh` that handles setup. Run it from your project root:

```bash
cd /path/to/your/project
/path/to/mg-cc-tools/codebase-health/install.sh --project
```

Or install globally (available in all projects):

```bash
/path/to/mg-cc-tools/codebase-health/install.sh --global
```

See each tool's README for detailed usage.

## Namespace

All commands use the `/mg:` prefix (e.g., `/mg:codebase-health`).
