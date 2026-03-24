# Codebase Structure

```
mg-cc-tools/
├── pyproject.toml              # Project config (uv, pytest markers)
├── CLAUDE.md                   # Claude Code instructions
├── README.md                   # Project readme
├── .gitignore
├── uv.lock
│
├── install/                    # Meta-installer tool
│   ├── scripts/mg-install-lib.py  # Core install logic (manifest, checksums, validation)
│   └── commands/install.md
│
├── codebase-health/            # Complex: scan → verify → implement pipeline
│   ├── commands/               # 4 command files (router + 3 pipeline steps)
│   ├── agents/                 # 14 scanner agents + implementor + TEMPLATE
│   ├── scripts/                # Python helpers for JSON findings I/O + analysis
│   ├── references/schema.md   # Shared data contract
│   └── install.sh
│
├── auto-doc/                   # Complex: scan → generate → verify pipeline
│   ├── commands/               # 6 command files (router + pipeline + add + script)
│   ├── agents/                 # 5 audience writers + scan-audience + verifier + TEMPLATE
│   ├── scripts/                # Python helpers for JSON scan I/O
│   ├── references/             # Schema, style guide, templates by audience
│   └── install.sh
│
├── gsd-patches/                # GSD workflow patches
│   ├── patches/                # Individual patch .md files
│   └── commands/
│
├── session-analyzer/           # Session transcript analysis
│   ├── cc_session_analyzer.py
│   ├── cc_session_compactor.py
│   ├── tests/
│   └── commands/
│
├── debug-triage/               # Simple: single command
├── update-backlog/             # Simple: single command
├── new-milestone-gsd/          # Simple: single command
├── cc-regression-test/         # Regression testing
├── create-context/             # Context creation
├── data-provider/              # Data provider
├── permission-hooks/           # Permission hooks
├── mg-gsd-wrappers/            # GSD wrappers
│
├── .claude/                    # Claude Code config for this repo
├── .planning/                  # GSD planning directory
└── .serena/                    # Serena config
```

## Key Pattern: Tool Anatomy
Every tool has: `tool.toml` (metadata), `install.sh` (deployment), `commands/*.md` (LLM prompts), and optionally `agents/`, `scripts/`, `references/`.
