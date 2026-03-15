# Codebase Concerns

**Analysis Date:** 2026-03-15

## Tech Debt

**Massively duplicated install script boilerplate:**
- Issue: Every tool's `install.sh` contains 60-80 lines of identical argument-parsing, mode-resolution, and validation boilerplate. The argument parsing block (`--project`, `--global`, `--target`, `--help`) is copy-pasted verbatim across all 10 install scripts with only the tool name and post-install steps varying.
- Files: `debug-triage/install.sh`, `new-milestone-gsd/install.sh`, `update-backlog/install.sh`, `codebase-health/install.sh`, `permission-hooks/install.sh`, `create-context/install.sh`, `gsd-patches/install.sh`, `mg-gsd-wrappers/install.sh`, `data-provider/install.sh`, `cc-regression-test/install.sh`
- Impact: Any change to install behavior (e.g., adding a new mode, fixing the `--target` crash documented below) must be applied in 10 places. High risk of drift when only some get updated.
- Fix approach: Extract a shared `lib/install-common.sh` that provides `parse_install_args()` and `resolve_target_dir()` functions. Each tool's `install.sh` would source it and only define tool-specific logic (file copying, sed replacements, scaffolding).

**No tests for codebase-health Python scripts:**
- Issue: The `codebase-health/scripts/` directory contains 12 Python scripts (3,300+ lines total) with zero test files. These scripts handle JSON I/O, import graph analysis (Tarjan's SCC), dependency analysis, code duplication scanning, and finding management -- all untested.
- Files: `codebase-health/scripts/add-finding.py`, `codebase-health/scripts/merge-findings.py`, `codebase-health/scripts/verify-finding.py`, `codebase-health/scripts/update-findings.py`, `codebase-health/scripts/split-findings.py`, `codebase-health/scripts/circular-deps.py`, `codebase-health/scripts/unused-deps.py`, `codebase-health/scripts/lib/imports.py`, `codebase-health/scripts/lib/ignore.py`
- Impact: Algorithmic bugs in cycle detection, import resolution, or finding classification would go undetected. The `circular-deps.py` script uses Tarjan's SCC algorithm with manually tuned recursion limits -- a prime candidate for edge-case failures.
- Fix approach: Add a `codebase-health/scripts/tests/` directory with unit tests for at minimum: `add-finding.py` (JSON append/atomic-write), `merge-findings.py` (deduplication), `lib/imports.py` (Python/JS/Go/Rust import extraction), `lib/ignore.py` (pattern matching), `circular-deps.py` (cycle detection with known graphs), `unused-deps.py` (manifest parsing for all supported formats).

**No tests for data-provider Python scripts:**
- Issue: The `data-provider/scripts/` directory contains 3 Python scripts (~1,000 lines) with no test files. `status.py` alone is 522 lines.
- Files: `data-provider/scripts/generate.py`, `data-provider/scripts/status.py`, `data-provider/scripts/summarize.py`
- Impact: Task generation, status aggregation, and report summarization logic is untested.
- Fix approach: Add `data-provider/scripts/tests/` with unit tests for each script.

**`_parse_pyproject_toml` uses regex instead of TOML parser:**
- Issue: `codebase-health/scripts/unused-deps.py` parses `pyproject.toml` with line-by-line regex matching instead of using Python's built-in `tomllib` (available since Python 3.11). The regex approach breaks on multi-line strings, inline tables, and nested arrays.
- Files: `codebase-health/scripts/unused-deps.py` (lines 183-222)
- Impact: Dependencies declared using TOML features like inline tables or multi-line arrays will be silently missed. Since the project targets Python 3.8+, `tomllib` is not available on all targets, but a stdlib-only fallback could handle more cases.
- Fix approach: Use `tomllib` when available (Python 3.11+) with a fallback to the current regex for older Python versions. Add a `try: import tomllib except ImportError:` guard.

## Known Bugs

**`--target` without argument crashes all install scripts:**
- Symptoms: Running any `install.sh --target` (without providing a path) causes a bash `unbound variable` error and a non-zero exit with an unhelpful message: `install.sh: line NN: $2: unbound variable`.
- Files: All 10 `install.sh` files. The pattern is `TARGET_DIR="$2"` followed by `shift 2` in the `--target)` case.
- Trigger: `./install.sh --target` (no path argument).
- Workaround: Always provide a path after `--target`.
- Fix: Add a guard before `shift 2`: `if [[ $# -lt 2 ]]; then echo "Error: --target requires a path"; exit 1; fi`.

**`PROJECT_PATH` variable uninitialized in some install scripts:**
- Symptoms: In `debug-triage/install.sh`, `new-milestone-gsd/install.sh`, and `update-backlog/install.sh`, the `PROJECT_PATH` variable is set inside the `--project)` case but never initialized to empty at the top of the script. With `set -u` (nounset), this would crash if the variable were referenced outside the `--project` code path. Currently safe because `${PROJECT_PATH:-.}` provides a default, but it is inconsistent with `codebase-health/install.sh` and `permission-hooks/install.sh` which properly initialize `PROJECT_PATH=""`.
- Files: `debug-triage/install.sh`, `new-milestone-gsd/install.sh`, `update-backlog/install.sh`
- Trigger: Currently does not trigger a crash, but any future code that references `$PROJECT_PATH` outside the `project)` case block would fail.
- Workaround: None needed currently.
- Fix: Add `PROJECT_PATH=""` after `MODE=""` in each script, matching the pattern used by the complex install scripts.

## Security Considerations

**Permission guard `{PROJECT_ROOT}` placeholder embedded at install time:**
- Risk: The `permission-guard.py` file contains a literal `PROJECT_ROOT = "{PROJECT_ROOT}"` placeholder that gets sed-replaced during installation. If the install script fails to replace it (e.g., `--global` mode sets `PROJECT_ROOT=""`), the guard falls back to `event.get("cwd", "")`. If neither provides a value, path-based guards are completely bypassed (all `check_outside_project` calls return `None` when `project_root` is empty).
- Files: `permission-hooks/hooks/permission-guard.py` (line 20), `permission-hooks/install.sh` (line 143)
- Current mitigation: For `--global` installs, `PROJECT_ROOT` is intentionally empty, and the hook event's `cwd` field provides a runtime fallback. The `check_outside_project` and `check_file_outside_project` functions early-return `None` when no root is available, meaning they allow rather than block. This is documented behavior.
- Recommendations: Consider logging a warning when both `PROJECT_ROOT` and `cwd` are empty, so users know the path guard is inactive. Alternatively, consider always requiring a project root.

**Permission guard regex bypasses via shell quoting:**
- Risk: The command tokenizer in `check_outside_project` splits on `[\s;|&]+` which does not handle shell quoting. A command like `cp file.txt "/etc/shadow"` tokenizes the path with quotes but `_TOKEN_STRIP_CHARS` strips those. However, more exotic shell constructs (subshells, command substitution, heredocs) are not parsed and could hide dangerous paths.
- Files: `permission-hooks/hooks/permission-guard.py` (lines 168, 239)
- Current mitigation: The guard is a best-effort safety net, not a sandbox. Users still see an approval prompt from Claude Code for many operations.
- Recommendations: Document the known limitations explicitly. Consider using `shlex.split()` for more robust tokenization (though it has its own edge cases with incomplete commands).

**`cc-regression-test/install.sh` modifies `settings.json` directly:**
- Risk: The `cc-regression-test/install.sh` script directly writes to `.claude/settings.json` using embedded Python, merging a hook entry. If another process or tool concurrently modifies settings.json, data could be lost (no file locking).
- Files: `cc-regression-test/install.sh` (lines 158-198)
- Current mitigation: Install scripts are run manually and infrequently, making races unlikely.
- Recommendations: Use atomic write (write to temp file, then `os.replace`) for the settings.json modification, matching the pattern used by the codebase-health scripts.

## Performance Bottlenecks

**`circular-deps.py` recursive Tarjan's SCC with manual recursion limit:**
- Problem: The Tarjan's SCC implementation uses recursive `strongconnect()` and manually sets `sys.setrecursionlimit(max(10000, len(graph) * 2))`. On large codebases (10,000+ files), this risks stack overflow or extreme memory use.
- Files: `codebase-health/scripts/circular-deps.py` (lines 97-141, especially line 135)
- Cause: Python's default recursion limit exists to prevent stack overflows. Doubling it based on graph size is a band-aid.
- Improvement path: Convert to an iterative Tarjan implementation. This eliminates the recursion limit concern entirely and is a well-known transformation.

**`unused-deps.py` reads every source file for each dependency:**
- Problem: The `_search_in_source_files` function is called once per dependency, and each call walks all source files. For a project with N dependencies and M source files, this is O(N*M) file reads.
- Files: `codebase-health/scripts/unused-deps.py` (lines 430-460)
- Cause: No pre-built index of file contents or imports. Each dependency check re-reads every source file.
- Improvement path: Build a single content index (or import index via `lib/imports.py`) on first pass, then check all dependencies against it. This reduces file I/O from O(N*M) to O(M).

## Fragile Areas

**sed-based path resolution in install scripts:**
- Files: All `install.sh` files that use `sed -i "s|...|...|g"` for placeholder replacement, particularly `codebase-health/install.sh` (lines 182-216), `gsd-patches/install.sh` (lines 123-129), `mg-gsd-wrappers/install.sh` (lines 128-132)
- Why fragile: sed replacements use `|` as the delimiter. If an install target path contains `|` characters (unlikely but possible), the sed command breaks silently. More critically, the `agents/` replacement in `codebase-health/install.sh` (line 194) uses a bare `sed -i "s|agents/|${AGENTS_ABSOLUTE}/|g"` which replaces ALL occurrences of the string `agents/` in the scan command file -- including any that appear in prose descriptions or examples, not just path references.
- Safe modification: When adding new placeholders, use `{UPPERCASE_PLACEHOLDER}` convention (already used for `{SCRIPTS_DIR}`, `{GLOBAL_CONFIG}`, etc.) rather than bare path prefixes. The bare `agents/` replacement is the exception and should be migrated to a `{AGENTS_DIR}` placeholder.
- Test coverage: Zero. No install script has any test.

**`mg-gsd-wrappers/install.sh` cross-tool dependency on `gsd-patches`:**
- Files: `mg-gsd-wrappers/install.sh` (lines 16, 101-106)
- Why fragile: This install script uses `REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"` to navigate to the parent directory and read `gsd-patches/patches/discuss-phase-check-remaining.md`. This is the ONLY install script that references another tool's files at install time, violating the "each tool is self-contained" convention stated in `CLAUDE.md`. If the repo structure changes (e.g., tools moved to a subdirectory), this breaks.
- Safe modification: Copy the needed patch file into `mg-gsd-wrappers/` directory at development time, or add it as a direct file in that tool's directory.
- Test coverage: Zero.

**Tarjan's SCC recursion on deep import chains:**
- Files: `codebase-health/scripts/circular-deps.py` (lines 109-141)
- Why fragile: The recursive `strongconnect` function will hit Python's stack limit on deep linear import chains (not just cycles). Even with the doubled recursion limit, a chain of 5000+ files importing each other linearly (A -> B -> C -> ...) exhausts the stack.
- Safe modification: Convert to iterative implementation.
- Test coverage: Zero.

## Scaling Limits

**Health scan pipeline performance on large codebases:**
- Current capacity: Designed for single-project codebases of moderate size (hundreds to low thousands of files).
- Limit: The `unused-deps.py` O(N*M) scan, `circular-deps.py` recursive SCC, and `vulture-scan.py`/`jscpd-scan.py`/`lizard-scan.py` external tool invocations each independently become slow on large monorepos.
- Scaling path: Introduce incremental scanning (only analyze changed files), build file content indexes, and parallelize independent scanner agents.

## Dependencies at Risk

**External CLI tool requirements for codebase-health:**
- Risk: The codebase-health pipeline requires 5 external CLI tools (`ruff`, `vulture`, `lizard`, `jscpd`, `pyright`) to be installed separately. None are declared as project dependencies -- they are listed only in the install summary output. If any tool is missing at scan time, the corresponding scanner agent silently produces empty results or errors.
- Impact: Users may run scans thinking they are comprehensive when entire categories are being skipped.
- Migration plan: Add explicit checks at scan time (not just install time) for each required tool, with clear error messages. Consider making the scanner agents more resilient by marking tool-dependent findings as "skipped" rather than silently omitting them.

## Missing Critical Features

**No uninstall mechanism:**
- Problem: There is no `uninstall.sh` for any tool. Files copied into `.claude/commands/mg/`, `.claude/codebase-health/`, etc. have no automated removal path. Stale command files from old versions can persist after upgrades.
- Blocks: Clean tool removal, version upgrades that rename or remove commands.

**No version tracking for installed tools:**
- Problem: After running `install.sh`, there is no record of which version of a tool was installed. If a user runs an old `install.sh` against a project that had a newer version, it silently downgrades.
- Blocks: Safe upgrades, detecting version mismatches between tools that depend on each other.

## Test Coverage Gaps

**Only permission-guard has tests:**
- What's not tested: All install scripts, all codebase-health Python scripts (12 files, 3,300+ lines), all data-provider Python scripts (3 files, 1,000+ lines), the cc-regression-test hook and trigger.
- Files: The sole test file is `permission-hooks/hooks/tests/test_permission_guard.py` (849 lines, thorough coverage of that one module).
- Risk: Any refactoring of JSON I/O scripts, import analysis, or install logic has no safety net.
- Priority: High for `codebase-health/scripts/lib/imports.py` and `codebase-health/scripts/lib/ignore.py` (shared libraries used by multiple scripts), `codebase-health/scripts/add-finding.py` and `codebase-health/scripts/merge-findings.py` (data integrity), Medium for install scripts (shell scripts are harder to unit-test but could use integration tests with temp directories).

**No integration tests for install scripts:**
- What's not tested: The entire install flow -- argument parsing, file copying, sed replacement, path resolution, scaffolding. The `--target` crash bug (documented above) would have been caught by even a basic smoke test.
- Files: All 10 `install.sh` files.
- Risk: Install-time bugs corrupt deployed command files or leave broken path references.
- Priority: Medium. A simple test harness that runs `install.sh --target /tmp/test-install` and verifies output files exist and contain resolved paths would catch most regressions.

---

*Concerns audit: 2026-03-15*
