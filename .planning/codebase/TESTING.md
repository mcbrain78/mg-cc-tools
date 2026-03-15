# Testing Patterns

**Analysis Date:** 2026-03-15

## Test Framework

**Runner:**
- pytest 9.0.2
- Config: `pyproject.toml` (implicit -- pytest auto-discovers from project root)
- No `pytest.ini`, `conftest.py`, or `setup.cfg` for pytest configuration

**Assertion Library:**
- Built-in `assert` statements (pytest native assertions)
- No third-party assertion libraries (no `hamcrest`, `assertpy`, etc.)

**Run Commands:**
```bash
python3 -m pytest                    # Run all tests
python3 -m pytest -v                 # Verbose output
python3 -m pytest path/to/test.py    # Run specific test file
python3 -m pytest -k "test_name"     # Run by name pattern
```

No watch mode or coverage configuration exists.

## Test File Organization

**Location:**
- Tests are **co-located** inside the tool they test, under a `tests/` subdirectory
- Current test locations:
  - `permission-hooks/hooks/tests/test_permission_guard.py` (154 tests)

**Naming:**
- Test files: `test_<module_name>.py`
- Test directory contains `__init__.py` (empty) to form a package: `permission-hooks/hooks/tests/__init__.py`

**Structure:**
```
permission-hooks/
├── hooks/
│   ├── permission-guard.py          # Source module
│   └── tests/
│       ├── __init__.py              # Empty package marker
│       └── test_permission_guard.py # Test file
```

## Test Structure

**Suite Organization:**
```python
"""Tests for permission-guard.py hook."""
import sys
import os
import pytest

# Module import via importlib (handles hyphenated filenames)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib
guard = importlib.import_module("permission-guard")

# Extract functions under test
check_command = guard.check_command
check_sensitive_in_command = guard.check_sensitive_in_command
check_file_path = guard.check_file_path

# ── Helpers ──────────────────────────────────────────────────────────────

def assert_blocked(command, expected_category=None):
    """Assert that a command triggers a category rule."""
    result = check_command(command)
    assert result is not None, f"Expected BLOCK but got PASS: {command}"

def assert_allowed(command):
    """Assert that a command passes all category rules."""
    result = check_command(command)
    assert result is None, f"Expected PASS but got BLOCK: {command}"

# ── Category: Git Branch & History ────────────────────────────────────

class TestGitBranchHistory:
    CAT = "Git Branch & History"

    def test_block_checkout_branch(self):
        assert_blocked("git checkout feature-x", self.CAT)

    def test_allow_checkout_file_restore(self):
        assert_allowed("git checkout -- file.txt")
```

**Patterns:**
- **No setup/teardown:** Tests are pure functions with no fixtures, no `setUp`/`tearDown`, no `@pytest.fixture`
- **No conftest.py:** No shared fixtures or plugins
- **Helper functions at module level:** `assert_blocked()`, `assert_bash_blocked()`, `assert_bash_allowed()`, `assert_allowed()` are defined once and used by all test classes
- **Class-level constants:** `CAT = "Git Branch & History"` stores the expected category for assertion reuse
- **One assertion per test:** Each test method tests a single command/scenario (except `test_allow_branch_list` which tests 4 related variants)
- **Descriptive test names:** `test_block_checkout_branch`, `test_allow_cherry_pick_recovery`, `test_still_block_other_home_paths`

## Importing Modules with Hyphens

Because Python scripts use kebab-case filenames (`permission-guard.py`), importing requires `importlib`:

```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib
guard = importlib.import_module("permission-guard")

# Extract specific functions for convenience
check_command = guard.check_command
check_file_path = guard.check_file_path
```

Use this pattern when writing tests for any kebab-case script in this project.

## Mocking

**Framework:** Not used

**Patterns:**
- No mocking anywhere in the test suite
- Tests call real functions with string inputs and check return values
- The permission-guard functions are pure (no I/O, no side effects) so they test cleanly without mocks

**What NOT to Mock:**
- Pure functions that take strings and return tuples/None -- test them directly

**When Mocking Would Be Needed:**
- For scripts that do file I/O (`add-finding.py`, `merge-findings.py`), mocking or temp directories would be appropriate
- For scripts that shell out to external tools (`vulture-scan.py`, `jscpd-scan.py`, `pyright-scan.py`, `lizard-scan.py`), subprocess mocking would be needed
- None of these have tests yet

## Fixtures and Factories

**Test Data:**
- String literals used directly in test methods:
  ```python
  def test_block_checkout_branch(self):
      assert_blocked("git checkout feature-x", self.CAT)
  ```
- No fixture files, no factory functions, no test data directories
- File path tests use hardcoded paths: `"/home/user/project/.env"`, `"/home/user/myproject"`
- Class-level `PROJECT` constant for path-based tests:
  ```python
  class TestOutsideProject:
      PROJECT = "/home/user/myproject"
  ```

**Location:**
- No dedicated fixture directory. All test data is inline.

## Coverage

**Requirements:** None enforced
- No coverage configuration in `pyproject.toml`
- No `pytest-cov` in dependencies
- `.coverage` and `htmlcov/` are in `.gitignore` (suggesting coverage was run at some point)

**View Coverage:**
```bash
python3 -m pytest --cov=permission-hooks/hooks  # Would need pytest-cov installed
```

## Test Types

**Unit Tests:**
- All 154 tests are pure unit tests
- Test individual functions in isolation with string inputs
- No database, no filesystem, no network access
- Extremely fast execution (all pure computation)

**Integration Tests:**
- Not present
- The Python scripts that do I/O (`add-finding.py`, `merge-findings.py`, etc.) have no tests

**E2E Tests:**
- Not present
- The install scripts (`install.sh`) have no automated tests
- The `cc-regression-test` tool appears to be a manual/semi-automated regression test for Claude Code hooks

## Common Patterns

**Testing "Blocked" Commands:**
```python
def test_block_force_push(self):
    assert_blocked("git push -f origin main", self.CAT)
    assert_blocked("git push --force origin main", self.CAT)
    assert_blocked("git push --force-with-lease origin main", self.CAT)
```

**Testing "Allowed" Commands:**
```python
def test_allow_normal_push(self):
    assert_allowed("git push origin main")
    assert_allowed("git push")
```

**Testing Path Guards (return value checking):**
```python
def test_block_absolute_outside(self):
    result = check_outside_project(
        "cp file.txt /etc/config", self.PROJECT
    )
    assert result is not None
    assert "/etc/config" in result[1]
```

**Testing Sensitive File Detection:**
```python
def test_block_env_file(self):
    assert check_file_path("/home/user/project/.env") is not None

def test_allow_env_example(self):
    assert check_file_path("/home/user/project/.env.example") is None
```

**Dual-Layer Testing (command rules + sensitive file check):**
```python
def assert_bash_blocked(command, expected_category=None):
    """Assert that a command is blocked by category rules OR sensitive file check."""
    result = check_command(command)
    if result is not None:
        if expected_category:
            assert result[1] == expected_category
        return result
    sens = check_sensitive_in_command(command)
    assert sens is not None, f"Expected BLOCK but got PASS: {command}"
    return sens
```

## Test Categorization

Tests are organized by **security category** matching the production code's `CATEGORIES` dict:

| Test Class | Category | Count |
|---|---|---|
| `TestGitBranchHistory` | Git Branch & History | 16 |
| `TestGitDestructiveRemote` | Git Destructive Remote | 10 |
| `TestGitHubCLI` | GitHub CLI | 8 |
| `TestPackagePublishing` | Package Publishing | 5 |
| `TestInfrastructure` | Infrastructure | 2 |
| `TestDestructiveFilesystem` | Destructive Filesystem | 8 |
| `TestSecretsCredentials` | Secrets & Credentials | 22 |
| `TestSystemOperations` | System Operations | 11 |
| `TestReadOnlyGit` | (allowed commands) | 6 |
| `TestOutsideProject` | Out-of-project guard | 18 |
| `TestSensitiveFilePaths` | File path guard | 22 |
| `TestFileOutsideProject` | File outside project | 14 |
| `TestClaudeMemoryExemption` | Claude internal exemption | 12 |

## Untested Areas

**Scripts with no tests:**
- `codebase-health/scripts/add-finding.py` - JSON append logic
- `codebase-health/scripts/merge-findings.py` - Deduplication, ID assignment, summary computation
- `codebase-health/scripts/verify-finding.py` - Verification recording (append, single, batch modes)
- `codebase-health/scripts/update-findings.py` - Implementation status updates
- `codebase-health/scripts/split-findings.py` - Finding filtering and markdown generation
- `codebase-health/scripts/circular-deps.py` - Tarjan's SCC, god module detection, layering violations
- `codebase-health/scripts/unused-deps.py` - Manifest parsing, usage searching, classification
- `codebase-health/scripts/lib/imports.py` - Import extraction for Python/JS/TS/Go/Rust
- `codebase-health/scripts/lib/ignore.py` - Gitignore-style pattern matching, file walking
- `codebase-health/scripts/vulture-scan.py` - Vulture wrapper
- `codebase-health/scripts/jscpd-scan.py` - jscpd wrapper
- `codebase-health/scripts/pyright-scan.py` - Pyright wrapper
- `codebase-health/scripts/lizard-scan.py` - Lizard wrapper
- `data-provider/scripts/generate.py` - Task file generation
- `data-provider/scripts/status.py` - Task file CRUD operations
- `data-provider/scripts/summarize.py` - Coverage report generation
- `permission-hooks/hooks/permission-guard.py` `main()` function - Hook stdin/stdout integration
- All `install.sh` scripts - Bash installation logic

**Where to add tests for new scripts:**
- Create `<tool>/scripts/tests/` directory with `__init__.py`
- Name test file `test_<script_name_snake_case>.py`
- Follow the pattern in `permission-hooks/hooks/tests/test_permission_guard.py`
- For scripts with I/O, use `tmp_path` pytest fixture or `tempfile.mkdtemp()`

---

*Testing analysis: 2026-03-15*
