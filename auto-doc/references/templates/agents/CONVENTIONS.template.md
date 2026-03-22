<!-- DIATAXIS: reference -->
<!-- AUDIENCE: agents -->

# Conventions

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Naming Conventions
<!-- PURPOSE: Explicit rules for naming files, functions, variables, and classes.
     Agents MUST follow these conventions when generating or modifying code.
     Each convention includes correct and incorrect examples. -->
<!-- EXAMPLE:
### File Naming

- Python modules: `snake_case.py`
- Test files: `test_{module_name}.py` (mirrors the source file name)
- Config files: `config.yaml`, `config.example.yaml`

| Correct | Incorrect | Rule |
|---------|-----------|------|
| `ingest.py` | `Ingest.py`, `ingestStage.py` | Lowercase snake_case for modules |
| `test_ingest.py` | `ingest_test.py`, `TestIngest.py` | `test_` prefix matches pytest discovery |
| `weighted_sum.py` | `WeightedSum.py`, `ws.py` | Descriptive snake_case, no abbreviations |

### Function Naming

- Public functions: `snake_case` with verb prefix
- Private functions: `_snake_case` with leading underscore
- MUST use descriptive names: `run_ingest`, `validate_record`, `get_connection`
- MUST NOT use generic names: `process`, `handle`, `do_thing`

| Correct | Incorrect | Rule |
|---------|-----------|------|
| `run_ingest(config, input_dir)` | `ingest(c, d)` | Verb prefix, descriptive parameters |
| `validate_record(record, rules)` | `check(r)` | Full words, no single-letter params |
| `_parse_csv_row(line)` | `parse_csv_row(line)` | Leading underscore for internal helpers |

### Class Naming

- Classes: `PascalCase`
- Abstract base classes: `Base{Name}` prefix
- MUST NOT suffix with `Manager`, `Handler`, `Helper` unless genuinely warranted

| Correct | Incorrect | Rule |
|---------|-----------|------|
| `BaseModel` | `ModelBase`, `AbstractModel` | `Base` prefix for ABCs |
| `WeightedSumModel` | `WeightedSumScorer` | Match the model registry naming |
| `BatchRun` | `BatchRunManager` | No unnecessary suffixes |

### Variable Naming

- Local variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- MUST NOT use single-letter variables except for loop indices (`i`, `j`)

| Correct | Incorrect | Rule |
|---------|-----------|------|
| `record_count` | `rc`, `cnt` | No abbreviations |
| `MODELS` | `models_registry` | Module-level constants are UPPER_SNAKE |
| `batch_id` | `bId`, `bid` | No camelCase, no ambiguous abbreviations |
-->

## Code Patterns
<!-- PURPOSE: Established patterns used throughout the codebase. Agents MUST
     recognize and follow these patterns when modifying or extending code.
     Each pattern includes a concrete code example and explains why the
     pattern exists. -->
<!-- EXAMPLE:
### Atomic JSON I/O

All JSON file operations MUST use the atomic write pattern to prevent corruption
on crash or concurrent access.

```python
import json
import os
import tempfile

def save_json(path: str, data: dict) -> None:
    """Write JSON atomically via temp file + os.replace."""
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile(
        mode="w", dir=dir_name, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name
    os.replace(tmp_path, path)
```

**Why:** Direct `open(path, "w")` followed by `json.dump()` creates a window
where the file is empty or partially written. `os.replace()` is atomic on
POSIX systems.

### Registry Pattern

New implementations (models, validators, output writers) MUST be registered
in a module-level dict for dynamic dispatch.

```python
# models/__init__.py
MODELS: dict[str, type[BaseModel]] = {
    "weighted_sum": WeightedSumModel,
    "llm": LLMScorer,
}
```

**Why:** Config-driven model selection requires name-to-class mapping. The
registry pattern keeps this explicit and discoverable.

### Config Loading

Configuration MUST be loaded once at startup and passed as a dict to all
functions. MUST NOT use module-level globals or singletons for config.

```python
# Correct
def run_ingest(config: dict, input_dir: str) -> BatchRun:
    timeout = config.get("timeout", 30)

# Incorrect
import config  # Module-level import of config values
def run_ingest(input_dir: str) -> BatchRun:
    timeout = config.TIMEOUT  # Hidden dependency
```
-->

## Do / Don't Rules
<!-- PURPOSE: Explicit do/don't pairs with concrete examples. Agents MUST
     follow these rules when generating code. Each rule includes a correct
     and incorrect code example to eliminate ambiguity. -->
<!-- EXAMPLE:
| Rule | Do (Correct) | Don't (Incorrect) |
|------|-------------|-------------------|
| Use parameterized queries | `cursor.execute("SELECT * FROM t WHERE id=?", (id,))` | `cursor.execute(f"SELECT * FROM t WHERE id={id}")` |
| Return typed results | `def score(record: dict) -> float:` | `def score(record):` |
| Raise specific exceptions | `raise ValueError("field 'name' is required")` | `raise Exception("error")` |
| Use pathlib or os.path | `os.path.join(base, "data", name)` | `f"{base}/data/{name}"` |
| Log with structured data | `logger.info("Processed batch", extra={"batch_id": bid, "count": n})` | `logger.info(f"Processed batch {bid} with {n} records")` |
| Handle missing config keys | `config.get("timeout", 30)` | `config["timeout"]` |
| Close resources explicitly | `with get_connection(db) as conn:` | `conn = get_connection(db)  # Never closed` |
-->

## Import Conventions
<!-- PURPOSE: How imports are organized within each file. Agents MUST follow
     this ordering when adding or modifying imports. Consistent import style
     prevents merge conflicts and makes dependencies scannable. -->
<!-- EXAMPLE:
### Import Order

1. Standard library imports
2. Third-party library imports (if any)
3. Local imports (project modules)

Each group separated by a blank line. Within each group, sorted alphabetically.

```python
# Standard library
import json
import os
from pathlib import Path

# Third-party (rare in this project)
import yaml

# Local
from lib.db import get_connection, atomic_write
from models.base import BaseModel
```

### Import Style

- MUST use `from module import name` for specific items
- MUST NOT use `from module import *`
- SHOULD use absolute imports, not relative imports
- MUST NOT import from `__init__.py` internal structure

| Correct | Incorrect | Rule |
|---------|-----------|------|
| `from lib.db import get_connection` | `from lib.db import *` | Explicit imports only |
| `from models.base import BaseModel` | `from .base import BaseModel` | Absolute imports preferred |
| `import json` | `from json import loads, dumps` | Import module for stdlib with many uses |
-->

## Error Handling Conventions
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: How errors are raised, caught, and logged throughout the codebase.
     Agents MUST follow these patterns to maintain consistent error behavior. -->
<!-- EXAMPLE:
### Error Raising

- MUST raise `ValueError` for invalid input data
- MUST raise `FileNotFoundError` for missing files (not generic `OSError`)
- MUST include the invalid value in the error message
- MUST NOT catch and re-raise without adding context

```python
# Correct
if not os.path.isdir(input_dir):
    raise FileNotFoundError(f"Input directory not found: {input_dir}")

# Incorrect
if not os.path.isdir(input_dir):
    raise Exception("Directory not found")
```

### Error Handling

- MUST catch specific exceptions, not bare `except:`
- MUST log errors before re-raising when adding context
- SHOULD use `try/except/else` when the success path needs separation

```python
# Correct
try:
    data = load_json(path)
except json.JSONDecodeError as e:
    logger.error("Invalid JSON in %s: %s", path, e)
    raise ValueError(f"Cannot parse {path}") from e
```
-->

## Logging Conventions
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: How logging is used across the codebase. Agents MUST follow
     these conventions to ensure logs are useful for debugging and monitoring. -->
<!-- EXAMPLE:
### Log Levels

| Level | When to Use | Example |
|-------|-------------|---------|
| `DEBUG` | Internal state, variable values | `logger.debug("Loaded %d records from %s", count, path)` |
| `INFO` | Pipeline progress, stage completion | `logger.info("Ingest complete: %d records", count)` |
| `WARNING` | Recoverable issues, fallback behavior | `logger.warning("OpenAI API unavailable, skipping LLM scorer")` |
| `ERROR` | Unrecoverable failures within a stage | `logger.error("Failed to write to PostgreSQL: %s", err)` |

### Logger Creation

- MUST use `logging.getLogger(__name__)` per module
- MUST NOT use `print()` for operational output
- MUST NOT configure logging in library modules (only in `cli.py`)

```python
import logging

logger = logging.getLogger(__name__)
```
-->
