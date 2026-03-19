# Install Command v1.1 — Two-Stage Install & Context Efficiency

## Problem Statement

v1.0 of `/mg:install` has two categories of issues discovered during real-world testing:

### 1. Two-stage install gap

Some tools require post-install configuration that needs a Claude Code context (modifying settings.json, applying patches interactively). Currently:

- **permission-hooks**: installs files via install.sh, then the user must separately run `/mg:install-permission-hooks` in the target project. This is unintuitive — two installs in two different Claude environments.
- **gsd-patches**: was marked `exclude = true` because it needs interactive patch application. With a post-install step, it can be a normal optional tool.
- **cc-regression-test**: bakes settings.json merge into install.sh (bash), which is fragile and inconsistent with how permission-hooks does it.
- **mg-gsd-wrappers**: installs a snapshot file into `commands/mg/` (not a command, clutters skill list) and has a cross-tool dependency on gsd-patches.

### 2. Context bloat

Session analysis of a single permission-hooks install showed 778K tokens consumed. Root causes:
- scan-status outputs full checksums (~5K per call) into conversation context
- adopt returns full manifest entries with checksums (~13K) and doesn't write the manifest
- validate scans ALL installed files in the target (118 issues), not just the installed tool
- validate has no `valid` field, causing LLM retry loops
- Placeholder regex flags template variables ({N}, {M}, {X}) as false positives
- LSP probe via `claude -p` subprocess hangs (can't spawn claude from within claude)

---

## Changes Already Implemented (this session)

The following context efficiency fixes are already done and tested:

- [x] `scan-status --output` — writes full details to file, compact summary to stdout
- [x] `adopt` — writes manifest directly, returns just tool names
- [x] `validate --tools --source --output` — scopes to installed tools, adds `valid` field
- [x] Placeholder regex requires 3+ chars (no more {N}, {M} false positives)
- [x] LSP probe replaced with settings.json file scan (instant, no subprocess)
- [x] `standard = false` field in tool.toml + manifest `standard_overrides`
- [x] "Edit standard install list" option in Step 3
- [x] Sibling directory scan replaces ~/.config/mg-cc-tools/targets.json
- [x] Status table with legend and standard/optional/excluded tiers
- [x] install.md: "validate once, don't retry" instruction
- [x] install.md: skip capabilities section when no tool requests LSP check

---

## Remaining Work — Two-Stage Install

### Concept

Every tool install follows the same pattern:

```
install.sh (copy files) → post-install.md (configure, if exists) → next tool
```

Per-tool sequential. If either stage fails, stop immediately.

### tool.toml Schema Extension

```toml
[tool]
description = "Claude Code permission guard hooks"
standard = false          # optional: not in bulk install (default: true)
exclude = true            # optional: internal-only (default: false)

[preflight]
required = ["python3"]
optional = ["lsp"]

[post_install]
script = "post-install.md"    # read from SOURCE by /mg:install, never copied to target

[detect]
paths = [".claude/permission-hooks/hooks/permission-guard.py"]  # for adopt flow
```

### Three-Tier Model

| Tier | `standard` | `exclude` | Bulk install | Table position |
|------|-----------|-----------|-------------|----------------|
| **Standard** | true (default) | false | Yes | Main section |
| **Single install** | false | false | No (by name only) | After `·` separator, marked `*` |
| **Excluded** | — | true | No | Below `─ ─` separator |

### Per-Tool Changes

#### permission-hooks
- **tool.toml**: add `[post_install] script = "post-install.md"`, add `[detect]`
- **File move**: `commands/install-permission-hooks.md` → `post-install.md` (tool root)
- **install.sh**: remove the line that copies install-permission-hooks.md to commands/mg/
- **Result**: no longer appears as `/mg:install-permission-hooks` in target skill list
- **post-install.md**: reads target path from /mg:install context, registers hooks in settings.json

#### gsd-patches
- **tool.toml**: change `exclude = true` → `standard = false`, add `[post_install] script = "post-install.md"`, add `[detect]`, **remove install.sh** (nothing to copy)
- **File move**: `commands/apply-gsd-patches.md` → `post-install.md` (tool root). No longer installed as a user command in the target.
- **Pattern**: execute-only tool — no install.sh stage, only post-install.md. The .md applies patches to GSD files already present in the target.
- **Re-apply after GSD updates**: user runs `/mg:install` again and selects gsd-patches. The post-install.md re-runs and re-applies patches. No separate "re-apply" command needed.
- **install.sh**: remove or make a no-op stub (tool.toml + install.sh pair is required for discovery — may need to keep a trivial install.sh, or update discovery to allow tool.toml + post-install.md as an alternative pair)

#### mg-gsd-wrappers
- **tool.toml**: add `standard = false`, add `[detect]`
- **install.sh**: move snapshot from `commands/mg/` to `.claude/mg-gsd-wrappers/references/`, update sed path
- **install.md table**: show note "Requires: gsd-patches" for this tool
- **No post-install needed** — pure file copy, just dependency ordering concern

#### cc-regression-test
- **tool.toml**: add `[post_install] script = "post-install.md"`, add `[detect]`
- **Extract**: settings.json merge logic from install.sh into post-install.md
- **install.sh**: simplified — just file copies, no settings.json manipulation

#### All other tools (8 tools)
- **tool.toml**: add `[detect]` section only
- **No other changes**

### Detection Paths for Adopt

| Tool | `[detect].paths` |
|------|-----------------|
| codebase-health | `[".claude/codebase-health/scripts/"]` |
| create-docs | `[".claude/create-docs/scripts/"]` |
| create-context | `[".claude/commands/mg/create-context.md"]` |
| data-provider | `[".claude/data-provider/scripts/"]` |
| debug-triage | `[".claude/commands/mg/debug-triage.md"]` |
| gsd-patches | `[".claude/gsd-patches/"]` |
| mg-gsd-wrappers | `[".claude/commands/mg/discuss-phase.md"]` |
| new-milestone-gsd | `[".claude/commands/mg/new-milestone-gsd.md"]` |
| update-backlog | `[".claude/commands/mg/update-backlog.md"]` |
| permission-hooks | `[".claude/permission-hooks/hooks/"]` |
| cc-regression-test | `[".claude/cc-regression-test/hooks/"]` |
| install | `[".claude/commands/mg/install.md"]` |

### mg-install-lib.py Changes

1. **`read_tool_toml()`**: parse `[post_install]` and `[detect]` sections
2. **`discover_tools()`**: allow `tool.toml + install.sh` OR `tool.toml + post-install.md` (for execute-only tools like gsd-patches)
3. **`adopt_tools()`**: check `[detect].paths` existence in addition to command file presence. A tool is detected if (all commands present) OR (all detect paths exist).
4. **`scan-status` output**: include `post_install` and `detect_paths` fields per tool (so install.md knows which tools need post-install)

### install.md Changes

1. **Step 6 (Execute Installs)**: change from batch to per-tool sequential:
   ```
   For each tool:
     1. If tool has install.sh: run install.sh --target "$TARGET_PATH/.claude"
        - If error: STOP, report, do not continue
     2. If tool has post_install script:
        - Read the .md from SOURCE directory (never copied to target)
        - Execute its instructions (runs in the current Claude context)
        - If error: STOP, report, do not continue
     3. Next tool
   ```
   Three install patterns:
   - **Copy only** (most tools): install.sh runs, no post-install
   - **Copy + configure** (permission-hooks, cc-regression-test): install.sh then post-install.md
   - **Execute only** (gsd-patches): no install.sh, only post-install.md
2. **Step 2b (Migration)**: adopt now also checks detect paths
3. **Status table**: show dependency notes for single-install tools

---

## Resolved Decisions

### 1. gsd-patches: execute-only tool (RESOLVED)

`apply-gsd-patches.md` moves from `commands/` to `post-install.md` at tool root. It is no longer installed as a user-facing command. gsd-patches becomes an execute-only tool — no install.sh copy stage, only post-install.md execution. Re-application after GSD updates is handled by running `/mg:install` again and selecting gsd-patches.

Discovery may need updating: currently requires `tool.toml + install.sh` pair. For execute-only tools, allow `tool.toml + post-install.md` as alternative.

---

## Open Decisions

### 2. mg-gsd-wrappers install order (RESOLVED)

Both tools are `standard = false` (single-install). The user selects them explicitly. The status table shows a dependency note for mg-gsd-wrappers: "Requires: gsd-patches". If the user selects mg-gsd-wrappers without gsd-patches installed, show the note and let the user install gsd-patches first. This is the natural flow — no ordering logic needed in /mg:install.

### 3. post-install.md target path passing (RESOLVED)

/mg:install already has `$TARGET_PATH` in its context. It reads the post-install.md from source and executes its instructions — the variable is naturally available. No special mechanism needed.

---

## Validation

- [ ] Install permission-hooks on road-runner via `/mg:install` — should complete in one step (no second command needed)
- [ ] `/mg:install-permission-hooks` no longer appears in road-runner's skill list
- [ ] Install gsd-patches on road-runner — should show as optional, run post-install interactively
- [ ] adopt detects permission-hooks via detect paths (no commands in commands/)
- [ ] Error in post-install.md stops the install flow
- [ ] Full test suite passes

---

## Scope

- **4 tools with real changes**: permission-hooks, gsd-patches, mg-gsd-wrappers, cc-regression-test
- **8 tools with mechanical changes**: add `[detect]` to tool.toml
- **mg-install-lib.py**: update read_tool_toml, adopt_tools, scan-status output
- **install.md**: per-tool sequential flow with post-install step
- **Tests**: update adopt tests, add post-install detection tests
