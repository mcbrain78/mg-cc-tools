# Phase 8: Install Tool Improvements - Research

**Researched:** 2026-03-19
**Domain:** Two-stage install (install.sh + post-install.md subagent), tool discovery, adopt flow, toml schema extensions
**Confidence:** HIGH

## Summary

Phase 8 transforms the mg-cc-tools installer from a single-stage copy-only model to a two-stage model where tools can optionally run a post-install.md step as a Claude Code subagent. This enables tools requiring interactive configuration (settings.json merges, GSD patch application) to be installed through the unified `/mg:install` command instead of requiring separate post-install commands.

The scope covers three layers: (1) mg-install-lib.py function changes (discover_tools, read_tool_toml, adopt_tools, compute_tool_checksums, scan-status output), (2) install.md orchestration rewrite (per-tool sequential with three install patterns and subagent spawning), and (3) per-tool changes across 12 tools (5 with substantive changes, 6 with mechanical [detect] additions, 1 with no toml changes but major file changes).

All decisions are locked in CONTEXT.md. The implementation is well-specified with clear patterns, no library exploration needed -- this is internal code refactoring with the existing Python stdlib + bash + markdown stack.

**Primary recommendation:** Implement in dependency order: mg-install-lib.py changes first (discover_tools must drop install.sh requirement BEFORE any tool removes its install.sh), then per-tool changes, then install.md rewrite, then tests.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Every tool install follows: install.sh (copy files) then post-install.md (configure, if exists), per-tool sequential
- If either stage fails, stop immediately -- do not continue with remaining tools (reverses v1.0 continue-on-error)
- Three install patterns: copy-only (most tools), copy+configure (permission-hooks, cc-regression-test), execute-only (gsd-patches)
- Post-install.md runs as a subagent (Agent tool), not inline
- install.md reads post-install.md from source, spawns a general-purpose Agent with prompt prefix containing target path and source path
- Subagent inherits all parent tools (Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion)
- Post-install.md references paths as provided context in natural language, not as shell variables
- Post-install.md is self-contained with no command frontmatter
- install.md must include Agent in allowed-tools (already added)
- TARGET_PATH = target project root; SOURCE_PATH = mg-cc-tools repo root (NOT the individual tool subdirectory)
- discover_tools() requires only tool.toml -- no stub install.sh files needed
- Install pattern derived from which files exist alongside tool.toml
- Implementation ordering: discover_tools() must be updated BEFORE any tool's install.sh is removed
- permission-hooks: standard = false, post-install.md from install-permission-hooks.md content rewrite, install.sh removes stale command copy
- gsd-patches: standard = false (was exclude = true), remove install.sh entirely, execute-only pattern, no [detect], stale file cleanup in post-install.md
- mg-gsd-wrappers: standard = false, move snapshot to .claude/mg-gsd-wrappers/references/, show "Requires: gsd-patches" note
- cc-regression-test: remains exclude = true, new post-install.md extracted from install.sh inline Python, install.sh simplified
- create-context: move context-template.snapshot from commands/mg/ to .claude/create-context/references/
- 6 tools get mechanical [detect] additions only
- Post-install.md must end with status marker: POST-INSTALL: SUCCESS or POST-INSTALL: FAILED: <reason>
- Create TEMPLATE-post-install.md that mandates this marker pattern
- install.md checks subagent returned text for the marker to determine success/failure
- On failure: show 1-line summary then full subagent output below
- No partial retry -- user selects tool again, both stages rerun
- No partial state tracking, no automated rollback

### Claude's Discretion
- Internal code organization within mg-install-lib.py (function structure, helper extraction)
- Test structure and organization for new tests
- Exact error message wording in install.md
- Order of mechanical [detect] additions across 6 tools
- Whether to batch mechanical tool.toml changes or do them one at a time

### Deferred Ideas (OUT OF SCOPE)
- v1.0 to v1.1 manifest migration path for existing targets
- CLAUDE.md update for cross-tool dependency acknowledgment
- Validation coverage for post-install artifacts (settings.json structural check)
- Updated status table example in install.md (implementer creates from spec)
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.11+ | tomllib, json, hashlib, pathlib, subprocess | Zero-dependency constraint -- already established |
| Bash | 5.x | install.sh scripts | Existing pattern for all tools |
| Claude Agent tool | N/A | post-install.md subagent execution | Built-in to Claude Code, no external dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tomllib | stdlib (3.11+) | Parse tool.toml [post_install] and [detect] sections | Already in mg-install-lib.py |
| pathlib.Path.glob | stdlib | Pattern matching for checksums (patches/**/*.md) | Already in compute_tool_checksums() |
| pytest | latest | Test runner | Already used for existing 48 tests |

### Alternatives Considered
None -- all decisions are locked. This is internal refactoring using the existing stack.

## Architecture Patterns

### Current Project Structure (relevant files)
```
install/
  scripts/
    mg-install-lib.py          # Main library (5 subcommands, ~950 lines)
    tests/
      test_mg_install_lib.py   # 48 tests, subprocess-based
  commands/
    install.md                 # /mg:install orchestration (436 lines)
  tool.toml
  install.sh

<tool-name>/
  tool.toml                   # Tool metadata + preflight + [post_install] + [detect]
  install.sh                  # Stage 1: file copies (optional for execute-only)
  post-install.md             # Stage 2: subagent instructions (optional, new)
  commands/                   # .md command files
  [patches/ | hooks/ | ...]   # Supporting resources
```

### Pattern 1: Three Install Patterns
**What:** Each tool follows one of three patterns based on which files exist alongside tool.toml
**When to use:** install.md Step 6 determines pattern per tool from scan-status output

| Files present | Pattern | Example tools | Who calls update-manifest |
|---|---|---|---|
| tool.toml + install.sh (no post-install.md) | Copy only | codebase-health, create-docs, etc. | install.sh |
| tool.toml + install.sh + post-install.md | Copy + configure | permission-hooks, cc-regression-test | install.sh |
| tool.toml + post-install.md (no install.sh) | Execute only | gsd-patches | install.md directly |

### Pattern 2: Post-install Subagent Invocation
**What:** install.md reads post-install.md from source, spawns Agent tool with prompt prefix
**When to use:** Any tool with post_install_script in scan-status output

```
Agent invocation prompt format:
  "Target project: <TARGET_PATH>\nSource directory: <SOURCE_PATH>\n\n<contents of post-install.md>"
```

Post-install.md must:
1. Be self-contained (no command frontmatter, no assumed context)
2. Reference paths via natural language ("the target project", "the source directory")
3. End with status marker: `POST-INSTALL: SUCCESS` or `POST-INSTALL: FAILED: <reason>`

### Pattern 3: tool.toml Schema Extension
**What:** New [post_install] and [detect] sections in tool.toml
**When to use:** Tools needing post-install or adopt detection

```toml
[tool]
description = "Claude Code permission guard hooks"
standard = false

[preflight]
required = ["python3"]

[post_install]
script = "post-install.md"

[detect]
paths = [".claude/permission-hooks/hooks/"]
```

### Pattern 4: Adopt Detection Logic (Updated)
**What:** adopt_tools() uses both command presence AND detect paths
**When to use:** adopt subcommand for pre-manifest installations

Detection rule: a tool is detected if:
- (has commands AND all commands present in target) OR
- (has detect.paths AND all detect paths exist in target)
- Both conditions require non-empty sets
- Execute-only tools (no commands, no detect paths) are skipped

### Anti-Patterns to Avoid
- **Removing install.sh before updating discover_tools():** gsd-patches loses its install.sh, but discover_tools() currently requires it. Update discover_tools() FIRST, then remove install.sh. Test discovery in between.
- **Shell variable placeholders in post-install.md:** Post-install.md is read as-is from source, not sed-resolved. Use natural language references to paths from the subagent prompt prefix.
- **Checking command-presence for execute-only tools in corrupt detection:** Execute-only tools write commands: [] in manifest. The corrupt check must guard for empty commands list to avoid false-flagging them.
- **Calling update-manifest from install.sh for execute-only tools:** Execute-only tools have no install.sh. install.md must call update-manifest directly after post-install completes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Manifest locking | Custom lock mechanism | Existing write_manifest_atomic() with fcntl.flock | Already handles concurrent writes, atomic replace |
| TOML parsing | Regex extraction | tomllib.load() (already used) | Handles all TOML edge cases |
| Subagent execution | Custom subprocess/API | Claude Code Agent tool | Built-in, handles tool inheritance, context isolation |
| File checksums | Custom hashing | Existing sha256_file() + compute_tool_checksums() | Already validated by 48 tests |

## Common Pitfalls

### Pitfall 1: Discovery Race Condition
**What goes wrong:** If discover_tools() still requires install.sh when gsd-patches' install.sh is removed, gsd-patches disappears from the tool list silently.
**Why it happens:** CONTEXT.md specifies removing install.sh from gsd-patches, but discover_tools() currently has `if os.path.isfile(toml_path) and os.path.isfile(install_path)`.
**How to avoid:** Update discover_tools() to require ONLY tool.toml BEFORE making any per-tool changes. Verify with a test that a tool with only tool.toml + post-install.md (no install.sh) is discovered.
**Warning signs:** Test `test_discovers_tools_with_toml_and_install_sh` currently asserts that a tool with only tool.toml is NOT discovered -- this test will need updating.

### Pitfall 2: Corrupt Detection for Execute-Only Tools
**What goes wrong:** Execute-only tools (like gsd-patches after migration) have commands: [] in manifest. The current corrupt check does `if manifest_commands else True` which correctly skips empty lists, BUT the scan-status output needs the `has_install_sh` field so install.md knows the pattern.
**Why it happens:** scan_status() currently doesn't report install pattern metadata.
**How to avoid:** Add `post_install` and `has_install_sh` fields to scan-status per-tool output. Guard corrupt detection: only check command-presence when manifest_entry.commands is non-empty.
**Warning signs:** gsd-patches showing as "Corrupt" after migration.

### Pitfall 3: Post-install.md Content Rewrite Scope
**What goes wrong:** Naively moving install-permission-hooks.md to post-install.md without stripping frontmatter, removing placeholders, rewriting path references.
**Why it happens:** The file looks similar but has fundamentally different execution context (subagent vs command).
**How to avoid:** Follow the CONTEXT.md rewrite checklist for each tool: strip frontmatter, remove sed placeholders, replace $ARGUMENTS with prompt-prefix path references, make self-contained.
**Warning signs:** Unresolved {SOURCE_DIR} or $ARGUMENTS in post-install.md.

### Pitfall 4: Stale File Cleanup Locations
**What goes wrong:** Putting cleanup logic in the wrong stage.
**Why it happens:** permission-hooks has install.sh (cleanup goes there), gsd-patches has no install.sh (cleanup goes in post-install.md).
**How to avoid:** Follow the rule: cleanup goes in whichever stage the tool actually has. permission-hooks: install.sh removes commands/mg/install-permission-hooks.md. gsd-patches: post-install.md removes commands/mg/apply-gsd-patches.md and .claude/gsd-patches/ directory.
**Warning signs:** Stale files remaining after v1.1 install over v1.0 install.

### Pitfall 5: Checksum Scope for gsd-patches
**What goes wrong:** After removing install.sh, gsd-patches checksum scope becomes post-install.md + patches/*.md. If patches/**/*.md is not added to CHECKSUM_INCLUDE, scan-status won't show "Modified" when patch templates change.
**Why it happens:** CHECKSUM_INCLUDE currently doesn't include patches/ files.
**How to avoid:** Add `patches/**/*.md` to CHECKSUM_INCLUDE list. Add `post-install.md` as a hardcoded root file check alongside install.sh in compute_tool_checksums().
**Warning signs:** Changing a patch .md file doesn't trigger "Modified" status.

### Pitfall 6: adopt_tools() Skips Commandless Tools
**What goes wrong:** Current adopt_tools() at line 757 does `if not commands: continue` -- this skips tools that have detect paths but no commands (like permission-hooks after removing the command copy).
**Why it happens:** v1.0 adopt logic only checks command presence.
**How to avoid:** Restructure adopt_tools() to check EITHER (commands AND all present) OR (detect paths AND all exist). Skip only when both are empty.
**Warning signs:** permission-hooks not detected by adopt even though hooks/ directory exists in target.

### Pitfall 7: mg-gsd-wrappers Snapshot Install Path
**What goes wrong:** Currently copies discuss-methodology.snapshot.md to commands/mg/ (appears in skill list). Need to move to .claude/mg-gsd-wrappers/references/.
**Why it happens:** Original install.sh predates the understanding that .snapshot files in commands/mg/ appear in the skill list.
**How to avoid:** Update install.sh to create .claude/mg-gsd-wrappers/references/ directory and copy snapshot there. Update sed resolution to use the new absolute path for {METHODOLOGY_SNAPSHOT}.
**Warning signs:** Snapshot still appearing in Claude Code skill list after install.

### Pitfall 8: Post-install Status Marker Parsing
**What goes wrong:** install.md fails to detect post-install success/failure because the marker text is not at the expected location in subagent output.
**Why it happens:** The Agent tool returns the subagent's full text output. The marker must be reliably at the end.
**How to avoid:** TEMPLATE-post-install.md must mandate the marker as the absolute last line. install.md searches for the marker pattern in the returned text.
**Warning signs:** Post-install that succeeded but install.md treats as failed (or vice versa).

## Code Examples

### mg-install-lib.py: Updated read_tool_toml()

```python
def read_tool_toml(tool_dir):
    """Read and parse tool.toml from a tool directory.

    Returns dict with keys: description, exclude, standard, required, optional,
    post_install_script, detect_paths.
    """
    toml_path = os.path.join(tool_dir, "tool.toml")
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    tool_section = data.get("tool", {})
    preflight_section = data.get("preflight", {})
    post_install_section = data.get("post_install", {})
    detect_section = data.get("detect", {})

    return {
        "description": tool_section.get("description", ""),
        "exclude": tool_section.get("exclude", False),
        "standard": tool_section.get("standard", True),
        "required": preflight_section.get("required", []),
        "optional": preflight_section.get("optional", []),
        "post_install_script": post_install_section.get("script"),
        "detect_paths": detect_section.get("paths", []),
    }
```

### mg-install-lib.py: Updated discover_tools()

```python
def discover_tools(source_dir):
    """Discover tools by scanning for tool.toml.

    Returns list of (tool_name, tool_dir) tuples, sorted by name.
    Install pattern derived from which files exist alongside tool.toml.
    """
    tools = []
    if not os.path.isdir(source_dir):
        return tools

    for entry in sorted(os.listdir(source_dir)):
        tool_dir = os.path.join(source_dir, entry)
        if not os.path.isdir(tool_dir):
            continue
        toml_path = os.path.join(tool_dir, "tool.toml")
        if os.path.isfile(toml_path):
            tools.append((entry, tool_dir))

    return tools
```

### mg-install-lib.py: Updated compute_tool_checksums()

```python
def compute_tool_checksums(tool_dir):
    """Compute SHA256 checksums for all source files in scope.

    Include patterns: commands/*, scripts/*.py, scripts/lib/*.py,
                      agents/*.md, references/**/*, patches/**/*.md
    Also always includes install.sh and post-install.md at root.
    """
    checksums = {}
    tool_path = Path(tool_dir)

    # Include hardcoded root files
    for root_file in ["install.sh", "post-install.md"]:
        path = tool_path / root_file
        if path.is_file():
            checksums[root_file] = sha256_file(str(path))

    # Glob each include pattern
    for pattern in CHECKSUM_INCLUDE:
        for path in sorted(tool_path.glob(pattern)):
            if not path.is_file():
                continue
            rel = str(path.relative_to(tool_path))
            if _is_excluded(rel):
                continue
            checksums[rel] = sha256_file(str(path))

    return checksums
```

### mg-install-lib.py: Updated adopt_tools() detection logic

```python
# Inside adopt_tools(), replace the current command-only check:
for tool_name, tool_dir in discover_tools(source_dir):
    if tool_name in manifest_tools:
        continue

    commands = get_tool_commands(tool_dir)
    toml_data = read_tool_toml(tool_dir)
    detect_paths = toml_data.get("detect_paths", [])

    # Detection: (has commands AND all present) OR (has detect paths AND all exist)
    commands_detected = (
        bool(commands) and
        all(os.path.isfile(os.path.join(cmd_dir, cmd)) for cmd in commands)
    )
    detect_detected = (
        bool(detect_paths) and
        all(os.path.exists(os.path.join(target_dir, p)) for p in detect_paths)
    )

    if not commands_detected and not detect_detected:
        continue

    # Tool is detected -- adopt it
    checksums = compute_tool_checksums(tool_dir)
    manifest_tools[tool_name] = {
        "version": version,
        "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "commands": commands,
        "source_checksums": checksums,
    }
    adopted_names.append(tool_name)
```

### tool.toml: [detect] section format

```toml
# For tools with installed support directories:
[detect]
paths = [".claude/codebase-health/scripts/"]

# For simple command-only tools:
[detect]
paths = [".claude/commands/mg/debug-triage.md"]

# For permission-hooks (detect by hooks directory):
[detect]
paths = [".claude/permission-hooks/hooks/"]
```

### Post-install.md: Template structure (TEMPLATE-post-install.md)

```markdown
# [Tool Name] -- Post-Install Configuration

<objective>
[What this post-install step does]
</objective>

<context>
The target project path and source directory path are provided at the top of this prompt.
Use "the target project" and "the source directory" to reference these paths.
</context>

<process>
## Step 1: [First step]
...

## Step N: [Last step]
...
</process>

<completion>
## Status

After all steps complete:

If all steps succeeded:
> POST-INSTALL: SUCCESS

If any step failed:
> POST-INSTALL: FAILED: <brief reason>

You MUST output exactly one of these two markers as the final line of your response.
</completion>
```

### install.md: Step 6 per-tool sequential pattern

```
For each tool in the final tool list:
  1. Read scan-status for this tool: has_install_sh, post_install

  2. If has_install_sh:
     Run: bash ./<tool-name>/install.sh --target "$TARGET_PATH/.claude"
     If exit code != 0: STOP, report "<tool-name> install FAILED"

  3. If post_install is not null:
     Read: ./<tool-name>/<post_install_script> (from source)
     Spawn Agent with prompt:
       "Target project: $TARGET_PATH\nSource directory: $SOURCE_PATH\n\n" + file_content
     Check returned text for POST-INSTALL marker:
       - Contains "POST-INSTALL: SUCCESS" -> continue
       - Contains "POST-INSTALL: FAILED:" -> STOP, show 1-line summary + full output
       - Neither marker found -> treat as FAILED

  4. If execute-only (no install.sh):
     Run: python3 "$MG_INSTALL_LIB" update-manifest \
       --target "$TARGET_PATH" --tool "<tool-name>" --source "./<tool-name>"

  5. Log: "<tool-name>... done"
  6. Next tool
```

## State of the Art

| Old Approach (v1.0) | Current Approach (v1.1) | Impact |
|-----|------|--------|
| install.sh only, separate commands for config | install.sh + post-install.md subagent | Single-step install for all tools |
| discover_tools() requires tool.toml + install.sh | discover_tools() requires only tool.toml | Enables execute-only tools |
| adopt via command presence only | adopt via commands OR detect paths | Detects tools installed to non-standard locations |
| gsd-patches excluded | gsd-patches optional (standard = false) | Accessible via unified installer |
| Batch install (continue-on-error) | Per-tool sequential (stop-on-error) | Prevents cascading failures |
| .snapshot files in commands/mg/ | .snapshot files in tool-specific references/ | No longer pollutes skill list |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via .venv/bin/python) |
| Config file | pyproject.toml (implicit) |
| Quick run command | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py -x` |
| Full suite command | `.venv/bin/python -m pytest` |

### Phase Requirements to Test Map

| Behavior | Test Type | Automated Command | File Exists? |
|----------|-----------|-------------------|-------------|
| discover_tools() finds tools with only tool.toml | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus::test_discovers_tools_with_toml_only -x` | Wave 0 (update existing test) |
| read_tool_toml() parses [post_install] and [detect] sections | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus::test_reads_post_install_and_detect -x` | Wave 0 |
| scan-status includes post_install and has_install_sh fields | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus::test_scan_status_includes_install_pattern -x` | Wave 0 |
| compute_tool_checksums() includes post-install.md | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestUpdateManifest::test_checksums_include_post_install -x` | Wave 0 |
| compute_tool_checksums() includes patches/**/*.md | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestUpdateManifest::test_checksums_include_patches -x` | Wave 0 |
| adopt_tools() detects via detect paths | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestAdopt::test_detects_by_detect_paths -x` | Wave 0 |
| adopt_tools() skips execute-only tools | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestAdopt::test_skips_execute_only_tools -x` | Wave 0 |
| Corrupt check skips empty commands list | unit | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py::TestScanStatus::test_no_corrupt_for_empty_commands -x` | Wave 0 |
| Existing tests still pass after refactor | regression | `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py -x` | Existing (48 tests) |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest install/scripts/tests/test_mg_install_lib.py -x`
- **Per wave merge:** `.venv/bin/python -m pytest`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
- [ ] `test_discovers_tools_with_toml_only` -- update existing test that asserts tool.toml-only is NOT discovered
- [ ] `test_reads_post_install_and_detect` -- new test for extended read_tool_toml()
- [ ] `test_scan_status_includes_install_pattern` -- new test for post_install/has_install_sh fields
- [ ] `test_checksums_include_post_install` -- new test for post-install.md in checksums
- [ ] `test_checksums_include_patches` -- new test for patches/**/*.md in checksums
- [ ] `test_detects_by_detect_paths` -- new test for adopt via detect paths
- [ ] `test_skips_execute_only_tools` -- new test for adopt skipping execute-only
- [ ] `test_no_corrupt_for_empty_commands` -- new test for corrupt guard
- [ ] `_make_tool()` helper update -- add post_install and detect_paths parameters

## Open Questions

1. **Test helper _make_tool() signature**
   - What we know: _make_tool() currently always creates install.sh. For testing execute-only tools, we need tools without install.sh.
   - What's unclear: Whether to add a boolean param (has_install_sh=True) or create a separate helper.
   - Recommendation: Add `has_install_sh=True` parameter to _make_tool(). When False, skip creating install.sh. This is the simplest change and matches the existing helper pattern. Also add `post_install_script=None` and `detect_paths=None` parameters.

2. **Exact post-install.md content for each tool**
   - What we know: CONTEXT.md specifies what to strip and rewrite for each tool, and we have the source commands to rewrite from.
   - What's unclear: The exact markdown content is not specified -- it must be crafted during implementation.
   - Recommendation: Use TEMPLATE-post-install.md as a structural guide. Each post-install.md follows the same pattern: objective, context (explains prompt prefix), process steps, completion (status marker).

## Implementation Dependency Order

This is the critical sequencing for the planner:

```
1. mg-install-lib.py changes (must come FIRST)
   a. Update read_tool_toml() for [post_install] + [detect]
   b. Update discover_tools() to drop install.sh requirement
   c. Update compute_tool_checksums() for post-install.md + patches/**/*.md
   d. Update adopt_tools() for detect paths
   e. Update scan_status() for post_install + has_install_sh fields + corrupt guard
   f. Update CHECKSUM_INCLUDE list
   g. Tests for all of the above

2. TEMPLATE-post-install.md (template before implementations)

3. Per-tool changes (can be parallel after #1 + #2)
   a. Mechanical [detect] additions (6 tools -- independent, can batch)
   b. permission-hooks (tool.toml + install.sh modify + post-install.md create)
   c. cc-regression-test (tool.toml + install.sh simplify + post-install.md create)
   d. gsd-patches (tool.toml + install.sh remove + post-install.md create)
   e. mg-gsd-wrappers (tool.toml + install.sh modify -- snapshot move)
   f. create-context (tool.toml + install.sh modify -- snapshot move)

4. install.md rewrite (depends on #1 for scan-status fields)
   a. Step 6 per-tool sequential with three patterns
   b. Step 6 subagent orchestration and status marker check
   c. Step 2b adopt with detect paths
   d. Status table updates
   e. Key constraints updates
```

## Specific File Change Summary

| File | Change Type | Lines (est) | Complexity |
|------|-------------|-------------|------------|
| install/scripts/mg-install-lib.py | Modify 5 functions | +80, -15 | Medium |
| install/scripts/tests/test_mg_install_lib.py | Add 8+ tests, update helper | +200 | Medium |
| install/commands/install.md | Rewrite Step 6, update Steps 2b/3/8 | +60, -30 | High (LLM prompt engineering) |
| TEMPLATE-post-install.md (new) | Create | +40 | Low |
| permission-hooks/tool.toml | Add standard, post_install, detect | +8 | Low |
| permission-hooks/install.sh | Remove command copy, add cleanup | +3, -2 | Low |
| permission-hooks/post-install.md (new) | Content rewrite from install-permission-hooks.md | +180 | Medium |
| gsd-patches/tool.toml | Change exclude to standard, add post_install | +5, -1 | Low |
| gsd-patches/install.sh | DELETE | -162 | Low |
| gsd-patches/post-install.md (new) | Content rewrite from apply-gsd-patches.md | +250 | High (complex logic) |
| cc-regression-test/tool.toml | Add post_install, detect | +6 | Low |
| cc-regression-test/install.sh | Remove settings.json merge | -40 | Low |
| cc-regression-test/post-install.md (new) | Settings.json merge instructions | +80 | Medium |
| mg-gsd-wrappers/tool.toml | Add standard, detect | +6 | Low |
| mg-gsd-wrappers/install.sh | Move snapshot to references/ dir | +5, -3 | Low |
| create-context/tool.toml | Add detect | +3 | Low |
| create-context/install.sh | Move snapshot to references/ dir | +5, -3 | Low |
| 6 tools tool.toml | Add [detect] section | +3 each (18 total) | Low |

## Sources

### Primary (HIGH confidence)
- Direct code inspection of mg-install-lib.py (954 lines), install.md (436 lines)
- Direct code inspection of all 12 tool.toml files
- Direct code inspection of install.sh for permission-hooks, gsd-patches, cc-regression-test, mg-gsd-wrappers, create-context
- Direct code inspection of install-permission-hooks.md and apply-gsd-patches.md (source commands for post-install.md rewrites)
- Direct code inspection of test_mg_install_lib.py (48 tests, all passing)
- docs/work-queue/todo/install-command-v1.1/PLAN.md (detailed specification)
- 08-CONTEXT.md (locked decisions from discussion session)

### Secondary (MEDIUM confidence)
- None needed -- all findings from direct code inspection

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all existing patterns
- Architecture: HIGH - all patterns directly observed in existing code + specified in CONTEXT.md
- Pitfalls: HIGH - identified from actual code analysis (line-level references to discover_tools, adopt_tools, scan_status)
- Implementation order: HIGH - dependency chain derived from actual code dependencies

**Research date:** 2026-03-19
**Valid until:** No expiry -- internal code patterns, no external dependency changes expected
