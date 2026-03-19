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

## Changes Already Implemented (v1.0 session)

The following context efficiency fixes are already in mg-install-lib.py and install.md (code infrastructure). Per-tool toml changes (`[detect]`, `[post_install]`, `standard = false`) are NOT done yet — those are in the "Remaining Work" section below.

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

### Constraints

- **Post-install scripts run from the mg-cc-tools source directory.** /mg:install reads post-install.md from source at install time — it is never copied to the target. Re-applying (e.g., gsd-patches after a GSD update) means running `/mg:install` from mg-cc-tools and selecting the tool again.
- **Post-install executes as a subagent.** install.md spawns a subagent (via Agent tool) for each post-install.md. This isolates post-install execution from the parent install flow — no context bleed from prior steps, clear success/failure result back to the parent. The invocation pattern:
  1. install.md reads the post-install.md file from source (e.g., `./permission-hooks/post-install.md`) using the Read tool
  2. install.md passes the file content as the Agent tool prompt, prefixed with context: `"Target project: $TARGET_PATH\nSource directory: $SOURCE_PATH\n\n" + file_content`
  3. The subagent executes the instructions and returns a result
  4. install.md checks the result — if the subagent reports failure, STOP
- **Post-install.md is self-contained.** No command frontmatter (it's not a registered skill). Written as a complete instruction document since the subagent has no prior context. Must not assume any variables or state beyond what is passed in the prompt prefix (target path, source path).
- **install.md must include `Agent` in `allowed-tools`** (already added).
- **No partial state tracking.** If post-install.md fails after install.sh succeeded, the manifest already has the tool entry and scan-status will show "✓ Current." The user fixes the issue and selects the tool again — install always runs both stages for any selected tool, there is no skip logic.
- **No automated rollback.** If post-install fails, the user fixes the issue and re-installs. No undo logic.

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
paths = [".claude/permission-hooks/hooks/"]  # for adopt flow
```

### Discovery Rule

A tool is any directory containing a `tool.toml`. What it *does* is determined by which files exist alongside it:

| Files present | Install pattern | Example |
|---|---|---|
| `tool.toml` + `install.sh` + `post-install.md` | Copy + configure | permission-hooks, cc-regression-test |
| `tool.toml` + `install.sh` | Copy only | most tools |
| `tool.toml` + `post-install.md` | Execute only | gsd-patches |

`discover_tools()` requires only `tool.toml` — no stub install.sh files needed.

### Three-Tier Model

| Tier | `standard` | `exclude` | Bulk install | Table position |
|------|-----------|-----------|-------------|----------------|
| **Standard** | true (default) | false | Yes | Main section |
| **Single install** | false | false | No (by name only) | After `·` separator, marked `*` |
| **Excluded** | — | true | No | Below `─ ─` separator |

### Per-Tool Changes

#### permission-hooks
- **tool.toml**: add `standard = false`, add `[post_install] script = "post-install.md"`, add `[detect]`
- **Create `post-install.md`** from `commands/install-permission-hooks.md` (not a simple move — content rewrite required):
  - Strip YAML frontmatter (`name:`, `description:`, `allowed-tools:`) — not a registered command
  - Replace `$ARGUMENTS` target path references with `$TARGET_PATH` (passed via subagent prompt prefix)
  - Remove `{SOURCE_DIR}` placeholder usage — the file is read directly from source, not sed-resolved at install time. Use relative paths from `$SOURCE_PATH` instead.
  - Rewrite as self-contained instructions that assume no prior context (subagent has a clean slate)
- **install.sh**: remove the line that copies install-permission-hooks.md to commands/mg/. Add cleanup: remove stale `install-permission-hooks.md` from target's `commands/mg/` if present (from pre-v1.1 installs).
- **Result**: no longer appears as `/mg:install-permission-hooks` in target skill list
- **post-install.md**: registers hooks in target's settings.json using target path from subagent prompt

#### gsd-patches

**How it works today (v1.0):**
gsd-patches is a tool that runs **from mg-cc-tools** and modifies GSD workflow files **in a target project**. It never copies files to the target — it reads structured patch templates (`patches/*.md` in the source tree), uses Claude's intelligence (Edit tool, anchor matching, conflict resolution) to find the right locations in the target's GSD files, and edits them in-place. The current install.sh copies the command .md and a duplicate of `patches/` into whichever `.claude/` directory the user targets (typically mg-cc-tools' own `.claude/` via `--project`). The user then invokes `/mg:apply-gsd-patches road-runner` from the mg-cc-tools project. The `{PATCHES_DIR}` / `{SOURCE_PATCHES_DIR}` distinction and the sync check (Step 0) exist because patches are duplicated between source and installed locations.

**v1.1 migration:**
- **tool.toml**: change `exclude = true` → `standard = false`, add `[post_install] script = "post-install.md"`
- **Create `post-install.md`** from `commands/apply-gsd-patches.md` (not a simple move — content rewrite required):
  - Strip YAML frontmatter — not a registered command
  - Remove `{PATCHES_DIR}` / `{SOURCE_PATCHES_DIR}` placeholders — no longer sed-resolved. Replace with `$SOURCE_PATH/gsd-patches/patches/` (source path passed via subagent prompt prefix)
  - Remove Step 0 (sync check) entirely — there is no installed copy vs source copy distinction anymore, always reading from source
  - Replace `$ARGUMENTS` target resolution with `$TARGET_PATH` from subagent prompt prefix
  - Rewrite as self-contained instructions for a subagent with no prior context
- **install.sh**: remove entirely. Nothing needs to be copied anywhere — not to the target, not to mg-cc-tools' own .claude/.
- **No `[detect]`**: nothing is installed to the target, so nothing to detect for adopt.
- **Manifest**: /mg:install writes a manifest entry (version, timestamp) in the target after post-install completes. scan-status compares version against source to show "Update available."
- **Re-apply after GSD updates**: user runs `/mg:install` and selects gsd-patches. post-install.md re-runs against the target. No separate command needed.
- **Adopt**: not adoptable — no persistent artifacts in target to detect.

#### mg-gsd-wrappers
- **tool.toml**: add `standard = false`, add `[detect]`
- **install.sh**: move snapshot from `commands/mg/` to `.claude/mg-gsd-wrappers/references/`, update sed path
- **install.md table**: show note "Requires: gsd-patches" for this tool
- **No post-install needed** — pure file copy, just dependency ordering concern

#### cc-regression-test
- **tool.toml**: add `[post_install] script = "post-install.md"`, add `[detect]`
- **Create `post-install.md`** (new file — extract and rewrite settings.json merge from install.sh):
  - Extract the inline Python settings.json merge logic from install.sh (adds `PreToolUse` hook for Bash matcher)
  - Rewrite as self-contained subagent instructions: read target settings.json, merge hook entry, write back
  - Use `$TARGET_PATH` from subagent prompt prefix, not shell variables
  - Handle edge cases: settings.json doesn't exist, hooks array doesn't exist, entry already present (idempotent)
- **install.sh**: simplified — just file copies and sed placeholder resolution, no settings.json manipulation

#### create-context
- **tool.toml**: add `[detect]`
- **install.sh**: change install destination of `context-template.snapshot` from `commands/mg/` to `.claude/create-context/references/`, update sed path in command files. Confirmed: `.snapshot` files in `commands/mg/` do appear in the skill list and should be moved out. Same fix as mg-gsd-wrappers.

#### All other tools (6 tools: codebase-health, create-docs, data-provider, debug-triage, new-milestone-gsd, update-backlog)
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
| mg-gsd-wrappers | `[".claude/commands/mg/discuss-phase.md"]` |
| new-milestone-gsd | `[".claude/commands/mg/new-milestone-gsd.md"]` |
| update-backlog | `[".claude/commands/mg/update-backlog.md"]` |
| permission-hooks | `[".claude/permission-hooks/hooks/"]` |
| cc-regression-test | `[".claude/cc-regression-test/hooks/"]` |

**Not adoptable:** gsd-patches (execute-only, no persistent artifacts to detect), install (excluded/internal — if present, manifest already exists)

### mg-install-lib.py Changes

1. **`read_tool_toml()`**: parse `[post_install]` and `[detect]` sections
2. **`discover_tools()`**: require only `tool.toml` for discovery. Derive install pattern from which files exist (install.sh, post-install.md, both, neither).
3. **`adopt_tools()`**: check `[detect].paths` existence in addition to command file presence. A tool is detected if (all commands present) OR (all detect paths exist). Skip tools with no detect paths and no commands (execute-only tools like gsd-patches).
4. **`scan-status` output**: include `post_install` and `has_install_sh` fields per tool (so install.md knows the install pattern)
5. **`compute_tool_checksums()`**: add `post-install.md` to scope (root file, like install.sh). Add `patches/**/*.md` to `CHECKSUM_INCLUDE`. For gsd-patches, this checksums post-install.md + patches/*.md — so scan-status shows "Update available" when patch templates change.

### install.md Changes

1. **Step 6 (Execute Installs)**: change from batch to per-tool sequential:
   ```
   For each tool:
     1. If tool has install.sh: run install.sh --target "$TARGET_PATH/.claude"
        - If error: STOP, report, do not continue
     2. If tool has post_install script:
        - Spawn a subagent (Agent tool) with:
          - The post-install.md content (read from source)
          - $TARGET_PATH and $SOURCE_PATH as context
        - Wait for subagent result
        - If error: STOP, report, do not continue
     3. For execute-only tools (no install.sh): call `update-manifest` after post-install completes
     4. Next tool
   ```
   Three install patterns:
   - **Copy only** (most tools): install.sh runs, no post-install. install.sh calls `update-manifest`.
   - **Copy + configure** (permission-hooks, cc-regression-test): install.sh then post-install.md subagent. install.sh calls `update-manifest`.
   - **Execute only** (gsd-patches): no install.sh, only post-install.md subagent. install.md calls `python3 "$MG_INSTALL_LIB" update-manifest` directly after post-install completes.
2. **Step 2b (Migration)**: adopt checks `[detect].paths` in addition to command presence. Execute-only tools (no detect paths, no commands) are skipped.
3. **Step 6 error handling**: change from continue-on-error to stop-on-error.
4. **Status table**: show dependency notes for single-install tools. Update example to reflect new tiers (gsd-patches and permission-hooks as optional `*`, not excluded).
5. **Key Constraint #5**: update excluded tools list (remove gsd-patches — now optional).
6. **Key Constraint #6**: add exception for execute-only tools (install.md calls update-manifest directly).

---

## Resolved Decisions

### 1. gsd-patches: execute-only tool
Execute-only — no install.sh, only post-install.md. Not adoptable (no persistent artifacts). Manifest entry written on completion for version tracking. Re-apply by running `/mg:install` and selecting it again.

### 2. Discovery: tool.toml is sufficient
`discover_tools()` requires only `tool.toml`. Install pattern derived from which files exist. No stub install.sh files.

### 3. mg-gsd-wrappers install order
Both tools are `standard = false`. Status table shows "Requires: gsd-patches" note. No ordering logic in /mg:install — user selects explicitly.

### 4. post-install.md target path passing
`$TARGET_PATH` is already in /mg:install context. No special mechanism needed.

### 5. No partial state tracking
If post-install.md fails after install.sh, the manifest has the tool entry. Re-running install re-runs both stages.

### 6. No automated rollback
User fixes the issue and re-installs.

### 7. Stop on error (not continue)
If install.sh or post-install.md fails for a tool, stop immediately. Do not continue with remaining tools. This reverses the v1.0 continue-on-error design — with post-install.md, a broken configuration could affect subsequent tools.

### 8. permission-hooks is `standard = false`
Requires interactive settings.json configuration via post-install.md. Should not fire during "Install all standard tools" — user selects it explicitly.

### 9. Stale file cleanup
install.sh should remove stale files from pre-v1.1 installs (e.g., `install-permission-hooks.md` from target's `commands/mg/`).

### 10. Post-install executes as subagent
Post-install.md runs in a spawned subagent (Agent tool), not inline. Clean context, no bleed from prior install steps. Post-install.md is self-contained with no command frontmatter — parameters passed via subagent prompt.

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

- **5 tools with real changes**: permission-hooks, gsd-patches, mg-gsd-wrappers, cc-regression-test, create-context
- **6 tools with mechanical changes**: add `[detect]` to tool.toml
- **mg-install-lib.py**: update discover_tools, read_tool_toml, adopt_tools, compute_tool_checksums, scan-status output
- **install.md**: per-tool sequential flow with post-install step, `update-manifest` call for execute-only tools
- **Tests**: update adopt tests, add post-install detection tests
