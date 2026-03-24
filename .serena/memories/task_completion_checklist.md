# What To Do When a Task Is Completed

After finishing code changes, run:

1. **Lint** the changed files:
   ```bash
   uv run ruff check .
   ```

2. **Run tests** relevant to the changed tool:
   ```bash
   uv run python -m pytest <tool>/scripts/tests/ --tb=short -q --no-header
   ```
   Or all tests:
   ```bash
   uv run python -m pytest --tb=short -q --no-header
   ```

3. If the change adds a new resource reference in a `.md` file, verify the corresponding `sed` replacement exists in the tool's `install.sh`.

4. Never pipe pytest output — it masks the exit code.
