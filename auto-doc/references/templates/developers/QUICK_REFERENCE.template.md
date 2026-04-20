<!-- DIATAXIS: reference -->
<!-- AUDIENCE: developers -->

# Quick Reference

## Commands
<!-- PURPOSE: A scannable lookup of every CLI command or slash command the
     project provides. Developers come here to find the exact syntax for a
     command they half-remember. Include brief description and usage example
     for each. -->
<!-- EXAMPLE:
| Command | Description | Example |
|---------|-------------|---------|
| `dataforge run` | Execute the full pipeline | `dataforge run --config config.yaml` |
| `dataforge run --stage ingest` | Run only the ingest stage | `dataforge run --stage ingest --input raw_files/` |
| `dataforge run --dry-run` | Validate pipeline without writing output | `dataforge run --dry-run` |
| `dataforge validate` | Check config file syntax | `dataforge validate config.yaml` |
| `dataforge report` | Generate summary from last run | `dataforge report --format json` |
| `dataforge version` | Print version and exit | `dataforge version` |
-->

## File Paths
<!-- PURPOSE: Quick lookup of important files and directories with their
     purpose. Developers use this to answer "where is the file that
     handles X?" without reading the full architecture docs. -->
<!-- EXAMPLE:
| Path | Purpose |
|------|---------|
| `cli.py` | CLI entry point, argument parsing |
| `config.yaml` | Runtime configuration (user-created, not committed) |
| `config.example.yaml` | Template config for new setups |
| `pipeline/ingest.py` | CSV file reading and raw record creation |
| `pipeline/transform.py` | Data validation, type conversion |
| `pipeline/score.py` | Model evaluation and scoring |
| `pipeline/output.py` | Result ranking and database writes |
| `models/base.py` | Abstract scoring model interface |
| `lib/db.py` | SQLite/PostgreSQL connection helpers |
| `lib/validators.py` | Field validation rules |
| `tests/conftest.py` | Shared test fixtures |
| `staging.db` | SQLite staging database (generated at runtime) |
-->

## Configuration
<!-- PURPOSE: Complete reference for all configuration options. Developers
     need to know what they can change, what the defaults are, and what
     values are valid. Organized for scanning, not reading. -->
<!-- EXAMPLE:
### config.yaml

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `input_dir` | `str` | `"raw_files/"` | Directory to scan for CSV files |
| `staging_db` | `str` | `"staging.db"` | Path to SQLite staging database |
| `output.database_url` | `str` | -- (required) | PostgreSQL connection string |
| `output.table` | `str` | `"results"` | Target table for ranked output |
| `scoring.models` | `list[dict]` | `[{"name": "weighted_sum"}]` | Scoring models to evaluate |
| `scoring.models[].name` | `str` | -- (required) | Model name (must match a registered model) |
| `scoring.models[].target_field` | `str` | -- | Field to score (model-specific) |
| `logging.level` | `str` | `"INFO"` | Log level: DEBUG, INFO, WARNING, ERROR |
| `logging.file` | `str` | `null` | Log file path (null = stdout only) |
-->

## API Surface
<!-- PURPOSE: Quick reference for key functions and classes that developers
     interact with most. Includes signatures, return types, and a one-line
     description. Not exhaustive -- focuses on the public API. -->
<!-- EXAMPLE:
### Pipeline Functions

```python
def run_ingest(config: dict, input_dir: str) -> BatchRun
```
Reads CSV files from `input_dir`, writes raw records to staging DB. Returns a `BatchRun` with record count.

```python
def run_transform(config: dict, batch_id: str) -> TransformResult
```
Validates and type-converts records for the given batch. Returns `TransformResult` with valid/invalid counts.

```python
def run_score(config: dict, batch_id: str) -> list[ScoredRecord]
```
Evaluates all configured scoring models against validated records. Returns scored records.

```python
def run_output(config: dict, scored: list[ScoredRecord]) -> OutputResult
```
Ranks scored records and writes to PostgreSQL. Returns `OutputResult` with row count.

### Database Helpers

```python
def get_connection(db_path: str) -> sqlite3.Connection
```
Returns a SQLite connection with WAL mode enabled. Thread-safe.

```python
def atomic_write(conn: sqlite3.Connection, table: str, rows: list[dict]) -> int
```
Writes rows in a single transaction. Returns number of rows written. Rolls back on any error.

### Model Interface

```python
class BaseModel(ABC):
    name: str
    def score(self, record: dict[str, Any]) -> float: ...
    def validate_config(self, config: dict) -> list[str]: ...
```
All scoring models extend `BaseModel`. `score()` returns a float between 0.0 and 1.0.
`validate_config()` returns a list of error messages (empty list = valid).
-->

## Environment Variables
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Reference for environment variables the system reads. Separate
     from config file options -- these are set in the shell or .env file
     and often contain secrets. -->
<!-- EXAMPLE:
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes (for output) | -- | PostgreSQL connection string |
| `OPENAI_API_KEY` | No | -- | API key for LLM scoring model |
| `DATAFORGE_CONFIG` | No | `"config.yaml"` | Override default config file path |
| `LOG_LEVEL` | No | `"INFO"` | Override config file log level |
-->

## Error Codes
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Reference for error codes or exit codes the system produces.
     Developers debugging failures need to quickly look up what an error
     code means and what to do about it. -->
<!-- EXAMPLE:
| Exit Code | Meaning | Common Cause |
|-----------|---------|-------------|
| `0` | Success | Pipeline completed normally |
| `1` | General error | Check stderr for details |
| `2` | Config error | Invalid or missing `config.yaml` |
| `3` | Ingest error | No CSV files found or format error |
| `4` | Database error | Cannot connect to PostgreSQL |
-->
