<!-- DIATAXIS: how-to + tutorial -->
<!-- AUDIENCE: developers -->

# Developer Guide

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Development Setup
<!-- PURPOSE: Get a new contributor from zero to a working development
     environment with all dependencies installed and verified. Every command
     must be copy-paste-ready -- no hunting for prerequisites. -->
<!-- EXAMPLE:
### Prerequisites

- Python 3.11+
- SQLite 3.39+ (included with Python)
- PostgreSQL 14+ (for output stage only; optional for development)

### Setup

```bash
# Clone and enter the project
git clone https://github.com/acme/dataforge.git
cd dataforge

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Verify installation
dataforge --version
# Expected: dataforge 1.2.0

# Run tests to confirm everything works
python3 -m pytest
# Expected: all tests pass (XX passed in ~10s)
```

### Configuration

Copy the example config and edit for your environment:

```bash
cp config.example.yaml config.yaml
```

For development, the defaults work without modification. See
[Configuration Reference](./QUICK_REFERENCE.md#configuration) for all options.
-->

## Project Structure
<!-- PURPOSE: Give developers a map of the codebase so they know where to
     find and place code. Each directory gets a one-line description of its
     purpose. -->
<!-- EXAMPLE:
```
dataforge/
├── cli.py                  # CLI entry point and argument parsing
├── config.yaml             # Runtime configuration (not committed)
├── config.example.yaml     # Template config for new setups
├── pipeline/
│   ├── __init__.py
│   ├── ingest.py           # CSV file reading and raw record creation
│   ├── transform.py        # Data validation and type conversion
│   ├── score.py            # Model evaluation and scoring
│   └── output.py           # Result ranking and database writes
├── models/
│   ├── base.py             # Abstract scoring model interface
│   ├── weighted_sum.py     # Default weighted-sum scoring model
│   └── llm_scorer.py       # Optional LLM-based scoring model
├── lib/
│   ├── db.py               # SQLite/PostgreSQL connection helpers
│   ├── validators.py       # Field validation rules
│   ├── reports.py          # JSON report generation
│   └── rate_limiter.py     # API rate limiting for external calls
├── tests/
│   ├── conftest.py         # Shared fixtures (tmp_db, sample_csv)
│   ├── test_ingest.py      # Ingest stage tests
│   ├── test_transform.py   # Transform stage tests
│   ├── test_score.py       # Scoring tests with mock models
│   └── test_output.py      # Output stage tests
└── pyproject.toml          # Project metadata and dependencies
```
-->

## Common Tasks
<!-- PURPOSE: A lookup table for the most frequent developer tasks. Maps
     "I want to..." goals to the specific files and patterns involved.
     Developers scan this before diving into code. -->
<!-- EXAMPLE:
| I want to... | File(s) to modify | Example |
|--------------|-------------------|---------|
| Add a new scoring model | `models/base.py`, `models/my_model.py` | See [Adding a New Scoring Model](#adding-a-new-scoring-model) |
| Add a validation rule | `lib/validators.py` | Add function, register in `VALIDATORS` dict |
| Change CSV parsing logic | `pipeline/ingest.py` | Modify `parse_row()` |
| Add a CLI flag | `cli.py` | Add `argparse` argument, pass to pipeline |
| Add a new output format | `pipeline/output.py`, `lib/reports.py` | Add writer function, register in `WRITERS` dict |
| Modify the staging schema | `lib/db.py:create_tables()` | Add column, update migration |
-->

## Adding a New Scoring Model
<!-- PURPOSE: Step-by-step guide for the most common extension pattern. Shows
     the complete workflow from creating the file to integrating and testing
     the new component. This is the "golden path" for contributors. -->
<!-- EXAMPLE:
### 1. Create the model file

```python
# models/percentile_scorer.py
from models.base import BaseModel

class PercentileScorer(BaseModel):
    """Scores records by percentile rank within each field."""

    name = "percentile"

    def score(self, record: dict[str, Any]) -> float:
        # Calculate percentile rank across all records for target field
        target = record[self.config["target_field"]]
        values = self._get_all_values(self.config["target_field"])
        rank = sum(1 for v in values if v <= target) / len(values)
        return round(rank, 4)
```

### 2. Register the model

```python
# models/__init__.py
from models.percentile_scorer import PercentileScorer

MODELS = {
    "weighted_sum": WeightedSumModel,
    "llm": LLMScorer,
    "percentile": PercentileScorer,  # Add this line
}
```

### 3. Configure

```yaml
# config.yaml
scoring:
  models:
    - name: percentile
      target_field: revenue
```

### 4. Write tests

```python
# tests/test_score.py
def test_percentile_scorer(tmp_db, sample_records):
    model = PercentileScorer(config={"target_field": "revenue"})
    scores = [model.score(r) for r in sample_records]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores)  # Percentile scores are monotonic
```

### 5. Verify end-to-end

```bash
dataforge run --config config.yaml --dry-run
# Expected: Pipeline completes with no errors, scores printed to stdout
```
-->

## Testing
<!-- PURPOSE: Explain how the test suite is organized, how to run tests at
     different scopes, and what conventions to follow when adding tests. -->
<!-- EXAMPLE:
### Running Tests

```bash
# Full suite
python3 -m pytest

# Single file
python3 -m pytest tests/test_ingest.py

# Single test
python3 -m pytest tests/test_ingest.py::test_parse_csv_with_headers -v

# With coverage
python3 -m pytest --cov=pipeline --cov-report=term-missing
```

### Test Conventions

- **File naming:** `test_{module_name}.py` matching the source file
- **Fixtures:** Shared fixtures live in `conftest.py`. Use `tmp_db` for database
  tests, `sample_csv` for ingest tests.
- **No external calls:** Mock all external APIs (OpenAI, PostgreSQL) in unit tests.
  Use `monkeypatch` or `unittest.mock.patch`.
- **Assert on behavior, not implementation.** Test that output is correct, not
  that a specific internal function was called.
-->

## Debugging Tips
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Practical techniques for diagnosing common development issues.
     Saves contributors time by pointing to the most useful debugging
     approaches specific to this codebase. -->
<!-- EXAMPLE:
### Pipeline fails silently

Run with verbose logging:

```bash
dataforge run --log-level DEBUG 2>&1 | tee debug.log
```

### Staging database is corrupted

Delete and recreate:

```bash
rm staging.db
dataforge run --stage ingest  # Re-ingest from raw files
```

### Tests pass locally but fail in CI

Check Python version. CI uses Python 3.11 pinned. Run locally with:

```bash
python3.11 -m pytest
```
-->

## Contributing Guidelines
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Standards for code contributions including branch naming, commit
     messages, and review expectations. Helps contributors submit PRs that
     match project conventions. -->
<!-- EXAMPLE:
### Branch Naming

- `feat/short-description` for new features
- `fix/short-description` for bug fixes

### Commit Messages

Use conventional commits: `feat:`, `fix:`, `test:`, `refactor:`, `chore:`.

### Before Submitting

- [ ] All tests pass: `python3 -m pytest`
- [ ] No lint errors: `ruff check .`
- [ ] New code has tests
- [ ] Config changes documented in QUICK_REFERENCE.md
-->
