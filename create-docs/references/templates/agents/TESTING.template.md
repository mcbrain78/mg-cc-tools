<!-- DIATAXIS: reference + how-to -->
<!-- AUDIENCE: agents -->

# Testing

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Test Structure
<!-- PURPOSE: Where tests live, how they are named, and how test discovery
     works. Agents MUST follow these conventions when creating or modifying
     test files. -->
<!-- EXAMPLE:
### Directory Layout

```
tests/
├── conftest.py             # Shared fixtures used across all test files
├── test_ingest.py          # Tests for pipeline/ingest.py
├── test_transform.py       # Tests for pipeline/transform.py
├── test_score.py           # Tests for pipeline/score.py
├── test_output.py          # Tests for pipeline/output.py
└── test_validators.py      # Tests for lib/validators.py
```

### Naming Rules

- Test files MUST be named `test_{module_name}.py`, matching the source module
- Test functions MUST be named `test_{behavior_description}`
- Test classes (if used) MUST be named `Test{ClassName}`
- MUST NOT use abbreviations in test names

| Source Module | Test File | Example Test |
|---------------|-----------|-------------|
| `pipeline/ingest.py` | `tests/test_ingest.py` | `test_ingest_creates_batch_run` |
| `lib/validators.py` | `tests/test_validators.py` | `test_validate_record_rejects_missing_required_field` |
| `models/weighted_sum.py` | `tests/test_score.py` | `test_weighted_sum_returns_normalized_score` |

### Test Discovery

- Framework: pytest 9.x
- Discovery: pytest finds all `test_*.py` files in `tests/` directory
- Configuration: `pyproject.toml` section `[tool.pytest.ini_options]`
- MUST NOT place test files outside the `tests/` directory
-->

## Running Tests
<!-- PURPOSE: Exact commands for running the test suite at different scopes.
     Agents MUST use these commands for verification. Each command includes
     expected output format. -->
<!-- EXAMPLE:
### Full Suite

```bash
python3 -m pytest
```
Expected output:
```
========================= test session starts =========================
collected 47 items
tests/test_ingest.py ........                                    [ 17%]
tests/test_transform.py ..........                               [ 38%]
tests/test_score.py ............                                  [ 63%]
tests/test_output.py .........                                   [ 82%]
tests/test_validators.py ........                                [100%]
======================== 47 passed in 3.21s ===========================
```

### Single File

```bash
python3 -m pytest tests/test_ingest.py
```

### Single Test

```bash
python3 -m pytest tests/test_ingest.py::test_ingest_creates_batch_run -v
```

### With Coverage

```bash
python3 -m pytest --cov=pipeline --cov=lib --cov-report=term-missing
```

### Stop on First Failure

```bash
python3 -m pytest -x
```
-->

## Test Patterns
<!-- PURPOSE: Established testing patterns used in this codebase. Agents MUST
     follow these patterns when writing new tests. Each pattern includes a
     complete code example showing correct usage. -->
<!-- EXAMPLE:
### Fixture: Temporary Database

All tests that need a database MUST use the `tmp_db` fixture. This creates
a fresh SQLite database in a temp directory, automatically cleaned up after
the test.

```python
# conftest.py
@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database with schema."""
    db_path = str(tmp_path / "test_staging.db")
    conn = get_connection(db_path)
    create_tables(conn)
    yield db_path
    conn.close()
```

Usage:

```python
def test_ingest_writes_records(tmp_db, sample_csv):
    config = {"staging_db": tmp_db}
    result = run_ingest(config, str(sample_csv))
    assert result.record_count == 3
```

### Fixture: Sample CSV File

Tests that need input CSV files MUST use the `sample_csv` fixture.

```python
# conftest.py
@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV file with 3 records."""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        "name,revenue,sector\n"
        "Acme Corp,1500000,Technology\n"
        "Globex,2300000,Manufacturing\n"
        "Initech,890000,Services\n"
    )
    return tmp_path  # Return directory, not file (ingest reads all CSVs in dir)
```

### Pattern: Mock External Services

All external API calls MUST be mocked in tests. Use `monkeypatch` for function
replacement.

```python
def test_llm_scorer_with_mock(monkeypatch):
    """LLM scorer returns mock score when API is mocked."""
    def mock_openai_call(prompt):
        return {"score": 0.85}

    monkeypatch.setattr("models.llm_scorer.call_openai", mock_openai_call)
    model = LLMScorer(config={"target_field": "description"})
    score = model.score({"description": "A technology company"})
    assert score == 0.85
```

### Pattern: Assert on Side Effects

When testing functions that write to database or files, assert on the written
data, not just the return value.

```python
def test_ingest_persists_to_database(tmp_db, sample_csv):
    config = {"staging_db": tmp_db}
    run_ingest(config, str(sample_csv))

    # Verify data was written to the database
    conn = get_connection(tmp_db)
    cursor = conn.execute("SELECT COUNT(*) FROM raw_records")
    assert cursor.fetchone()[0] == 3
    conn.close()
```
-->

## Writing a New Test
<!-- PURPOSE: Step-by-step guide for adding a test. Agents MUST follow these
     steps when generating test code to ensure tests integrate correctly
     with the existing suite. -->
<!-- EXAMPLE:
### Steps

1. **Identify the test file.** Find or create `tests/test_{module}.py`
   matching the source module being tested.

2. **Add imports:**
   ```python
   import pytest
   from pipeline.ingest import run_ingest  # Import the function under test
   ```

3. **Write the test function:**
   ```python
   def test_ingest_skips_empty_csv(tmp_path):
       """Ingest handles CSV files with only headers (no data rows)."""
       # Arrange: create a CSV with only a header
       csv_file = tmp_path / "empty.csv"
       csv_file.write_text("name,revenue,sector\n")

       # Act
       config = {"staging_db": str(tmp_path / "staging.db")}
       result = run_ingest(config, str(tmp_path))

       # Assert
       assert result.record_count == 0
       assert result.status == "empty"
   ```

4. **Use fixtures** for shared setup. If the test needs a database, add
   `tmp_db` as a parameter. If it needs sample data, add `sample_csv`.

5. **Run the test:**
   ```bash
   python3 -m pytest tests/test_ingest.py::test_ingest_skips_empty_csv -v
   ```

### Test Naming Convention

Format: `test_{function}_{scenario}_{expected_behavior}`

| Good Name | Why |
|-----------|-----|
| `test_ingest_skips_empty_csv` | Function + scenario + behavior |
| `test_validate_record_rejects_missing_name` | Function + input condition + outcome |
| `test_score_returns_zero_for_null_fields` | Function + edge case + return value |

| Bad Name | Why |
|----------|-----|
| `test_ingest` | Too vague -- what behavior? |
| `test_1` | Meaningless number |
| `test_it_works` | No useful information |
-->

## Integration Test Setup
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: How to set up and run integration tests that exercise multiple
     components together or connect to real external services. -->
<!-- EXAMPLE:
### Prerequisites

- PostgreSQL running locally on port 5432
- Test database created: `createdb dataforge_test`
- Environment variable: `TEST_DATABASE_URL=postgresql://localhost/dataforge_test`

### Running Integration Tests

```bash
# Integration tests are marked and excluded from default runs
python3 -m pytest -m integration

# Full suite including integration
python3 -m pytest --run-integration
```

### Integration Test Pattern

```python
@pytest.mark.integration
def test_full_pipeline_writes_to_postgres(tmp_db, sample_csv):
    """Full pipeline from CSV to PostgreSQL output."""
    config = load_config("config.test.yaml")
    result = run_pipeline(config)
    assert result.rows_written == 3

    # Verify in PostgreSQL
    conn = psycopg2.connect(os.environ["TEST_DATABASE_URL"])
    cursor = conn.execute("SELECT COUNT(*) FROM results")
    assert cursor.fetchone()[0] == 3
```
-->

## Test Data Management
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: How test data is created, managed, and cleaned up. Agents MUST
     follow these conventions to prevent test pollution and ensure test
     isolation. -->
<!-- EXAMPLE:
### Principles

- MUST NOT use production data in tests
- MUST NOT share state between tests (each test creates its own data)
- MUST use `tmp_path` fixture for all file-based test data
- MUST use `tmp_db` fixture for all database test data

### Sample Data Conventions

- Use realistic but fictional company names: "Acme Corp", "Globex", "Initech"
- Use plausible numeric values: revenue in millions, scores between 0 and 1
- MUST NOT use random data (tests must be deterministic)
- If randomness is needed for load testing, seed the RNG: `random.seed(42)`
-->
