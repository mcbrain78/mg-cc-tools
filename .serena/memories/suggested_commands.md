# Suggested Commands for Development

## Environment Setup
```bash
# Install dependencies (uses uv, not pip)
uv sync

# Activate virtual environment (alternative to uv run)
source .venv/bin/activate
```

## Testing
```bash
# Run all tests
uv run python -m pytest

# Run tests for a specific tool
uv run python -m pytest auto-doc/scripts/tests/
uv run python -m pytest codebase-health/scripts/tests/
uv run python -m pytest install/scripts/tests/
uv run python -m pytest session-analyzer/tests/

# Run a single test file
uv run python -m pytest auto-doc/scripts/tests/test_add_note.py

# Short output (recommended over piping)
uv run python -m pytest --tb=short -q --no-header

# Skip slow tests
uv run python -m pytest -m "not slow"
```

## Linting
```bash
# Lint check
uv run ruff check .

# Lint with auto-fix
uv run ruff check --fix .
```

## Dependency Management
```bash
# Add a dependency
uv add <package>

# Remove a dependency
uv remove <package>

# Add a dev dependency
uv add --optional dev <package>
```

## Git (standard Linux utils)
```bash
git status
git log --oneline -20
git diff
git add <files>
git commit -m "message"
```

## Important: Never pipe pytest output (e.g. `pytest | tail -20`) — this masks the exit code.
