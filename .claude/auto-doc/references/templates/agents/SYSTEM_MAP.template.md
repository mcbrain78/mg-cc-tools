<!-- DIATAXIS: reference -->
<!-- AUDIENCE: agents -->

# System Map

## Component Registry
<!-- PURPOSE: A complete table of every component in the system. Agents use
     this to resolve "which file handles X?" queries without scanning the
     filesystem. Every component MUST include its file path, purpose, and
     key exports. -->
<!-- EXAMPLE:
| Component | Path | Purpose | Key Exports | Dependencies |
|-----------|------|---------|-------------|-------------|
| CLI | `/opt/dataforge/cli.py` | Argument parsing, config loading, pipeline orchestration | `main()` | `pipeline/*` |
| Ingest | `/opt/dataforge/pipeline/ingest.py` | CSV file reading, raw record creation | `run_ingest(config, input_dir) -> BatchRun` | `lib/db.py` |
| Transform | `/opt/dataforge/pipeline/transform.py` | Type conversion, field validation | `run_transform(config, batch_id) -> TransformResult` | `lib/db.py`, `lib/validators.py` |
| Score | `/opt/dataforge/pipeline/score.py` | Model evaluation against validated records | `run_score(config, batch_id) -> list[ScoredRecord]` | `models/*`, `lib/db.py` |
| Output | `/opt/dataforge/pipeline/output.py` | Result ranking, PostgreSQL write, report generation | `run_output(config, scored) -> OutputResult` | `lib/db.py`, `lib/reports.py` |
| DB Helpers | `/opt/dataforge/lib/db.py` | Connection management, atomic writes | `get_connection(path) -> Connection`, `atomic_write(conn, table, rows) -> int` | stdlib `sqlite3` |
| Validators | `/opt/dataforge/lib/validators.py` | Field validation rule registry | `VALIDATORS: dict[str, Callable]`, `validate_record(record, rules) -> list[str]` | -- |
| Reports | `/opt/dataforge/lib/reports.py` | JSON/HTML report generation | `generate_report(results, format) -> str` | stdlib `json` |
| BaseModel | `/opt/dataforge/models/base.py` | Abstract scoring model interface | `BaseModel(ABC)` | -- |
| WeightedSum | `/opt/dataforge/models/weighted_sum.py` | Default weighted-sum scoring model | `WeightedSumModel(BaseModel)` | `models/base.py` |
-->

## File Structure
<!-- PURPOSE: A directory tree with one-line annotations for every significant
     file and directory. Agents MUST use this to understand the project layout.
     Every directory and every file that contains business logic MUST be listed. -->
<!-- EXAMPLE:
```
/opt/dataforge/
├── cli.py                      # Entry point: argument parsing and pipeline orchestration
├── config.yaml                 # Runtime configuration (user-created, not in git)
├── config.example.yaml         # Template configuration with documented defaults
├── pipeline/                   # Pipeline stages (executed sequentially)
│   ├── __init__.py             # Exports: run_pipeline()
│   ├── ingest.py               # Stage 1: CSV reading, raw record creation
│   ├── transform.py            # Stage 2: validation, type conversion
│   ├── score.py                # Stage 3: model evaluation
│   └── output.py               # Stage 4: ranking, DB write, reporting
├── models/                     # Scoring model implementations
│   ├── __init__.py             # Model registry: MODELS dict
│   ├── base.py                 # Abstract base class for all models
│   ├── weighted_sum.py         # Default: weighted sum of configured fields
│   └── llm_scorer.py           # Optional: OpenAI-based text field scoring
├── lib/                        # Shared utilities
│   ├── db.py                   # SQLite/PostgreSQL connection and atomic writes
│   ├── validators.py           # Field validation rule definitions
│   ├── reports.py              # Report generation (JSON, HTML)
│   └── rate_limiter.py         # Token bucket rate limiter for external APIs
├── tests/                      # Test suite (pytest)
│   ├── conftest.py             # Shared fixtures: tmp_db, sample_csv, mock_model
│   ├── test_ingest.py          # Ingest stage unit tests
│   ├── test_transform.py       # Transform stage unit tests
│   ├── test_score.py           # Scoring tests with mock models
│   └── test_output.py          # Output stage unit tests
└── pyproject.toml              # Project metadata, dependencies, tool config
```
-->

## Entry Points
<!-- PURPOSE: Every way to invoke the system. Agents MUST know all entry points
     to understand the system's boundaries. Each entry point MUST include the
     exact file path, invocation method, and what it triggers. -->
<!-- EXAMPLE:
| Entry Point | Type | Path | Invocation | Triggers |
|-------------|------|------|------------|----------|
| CLI main | Command line | `/opt/dataforge/cli.py:main()` | `dataforge run [--stage STAGE] [--config PATH]` | Full pipeline or single stage |
| CLI validate | Command line | `/opt/dataforge/cli.py:validate()` | `dataforge validate CONFIG_PATH` | Config file syntax check |
| Prefect flow | Scheduled | `/opt/dataforge/flows/pipeline_flow.py:pipeline_flow()` | Prefect agent (cron: `0 6 * * *`) | Full pipeline with monitoring |
| Python import | Library | `/opt/dataforge/pipeline/__init__.py:run_pipeline()` | `from pipeline import run_pipeline` | Programmatic pipeline execution |
-->

## Data Flow
<!-- PURPOSE: Step-by-step trace of data through the system. Each step MUST
     reference the exact function and file that performs the operation. Agents
     use this to understand causal chains when diagnosing issues or planning
     modifications. -->
<!-- EXAMPLE:
### Pipeline Execution (dataforge run)

1. `cli.py:main()` -- Parses CLI arguments, loads `config.yaml`
2. `cli.py:main()` -- Calls `pipeline.run_pipeline(config)` or individual stage
3. `pipeline/ingest.py:run_ingest(config, input_dir)`
   - Reads `*.csv` files from `input_dir`
   - Creates `RawRecord` per CSV row
   - Writes to `staging.db:raw_records` via `lib/db.py:atomic_write()`
   - Returns `BatchRun(batch_id, record_count)`
4. `pipeline/transform.py:run_transform(config, batch_id)`
   - Reads records from `staging.db:raw_records` WHERE `batch_id` matches
   - Applies `lib/validators.py:validate_record()` to each record
   - Type-converts fields per `config.field_types`
   - Updates `staging.db:raw_records.status` to `"validated"` or `"invalid"`
   - Writes invalid records to `errors.json`
   - Returns `TransformResult(valid_count, invalid_count)`
5. `pipeline/score.py:run_score(config, batch_id)`
   - Loads models from `models/` via `models.MODELS` registry
   - Calls `model.score(record)` for each validated record and each model
   - Writes scores to `staging.db:scores`
   - Returns `list[ScoredRecord]`
6. `pipeline/output.py:run_output(config, scored)`
   - Computes `final_rank` from aggregated scores
   - Writes ranked results to PostgreSQL `results` table
   - Calls `lib/reports.py:generate_report()` to create `report.json`
   - Returns `OutputResult(rows_written, report_path)`
-->

## API Surface
<!-- PURPOSE: Function signatures for all public functions and classes. Agents
     MUST use exact signatures when generating code that calls these functions.
     Each entry MUST include parameter types, return type, and side effects. -->
<!-- EXAMPLE:
### pipeline/ingest.py

```python
def run_ingest(config: dict, input_dir: str) -> BatchRun
```
- **Parameters:** `config` (parsed YAML config dict), `input_dir` (absolute path to CSV directory)
- **Returns:** `BatchRun(batch_id: str, record_count: int, started_at: datetime)`
- **Side effects:** Writes rows to `staging.db:raw_records`, creates `staging.db` if not exists
- **Raises:** `FileNotFoundError` if `input_dir` does not exist, `ValueError` if no CSV files found

### lib/db.py

```python
def get_connection(db_path: str) -> sqlite3.Connection
```
- **Parameters:** `db_path` (absolute path to SQLite database file)
- **Returns:** `sqlite3.Connection` with WAL mode enabled
- **Side effects:** Creates database file if not exists
- **Raises:** `sqlite3.OperationalError` on permission errors

```python
def atomic_write(conn: sqlite3.Connection, table: str, rows: list[dict]) -> int
```
- **Parameters:** `conn` (active connection), `table` (target table name), `rows` (list of column-value dicts)
- **Returns:** Number of rows written
- **Side effects:** Writes rows in a single transaction; rolls back on any error
- **Raises:** `sqlite3.IntegrityError` on constraint violations

### models/base.py

```python
class BaseModel(ABC):
    name: str
    config: dict

    @abstractmethod
    def score(self, record: dict[str, Any]) -> float: ...

    def validate_config(self, config: dict) -> list[str]: ...
```
- `score()` MUST return a float between 0.0 and 1.0
- `validate_config()` MUST return an empty list if config is valid
-->

## External Dependencies
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Services, APIs, or systems consumed by this project. Agents MUST
     know external boundaries to avoid generating code that assumes local-only
     operation. Each dependency MUST include the purpose, auth method, timeout,
     and fallback behavior. -->
<!-- EXAMPLE:
| Service | Purpose | Auth | Timeout | Fallback |
|---------|---------|------|---------|----------|
| PostgreSQL | Final output storage for ranked results | `DATABASE_URL` env var | 30s | Write to `fallback_results.json` |
| OpenAI API | LLM-based text field scoring | `OPENAI_API_KEY` env var | 30s per request | Skip LLM model, log warning |
| S3 | Raw CSV file storage (optional) | AWS credentials chain | 10s | Read from local `raw_files/` directory |
-->

## Configuration Schema
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Complete schema for all configuration files. Agents MUST
     reference this when generating or modifying configuration. Each field
     MUST include type, required/optional status, default value, and
     validation constraints. -->
<!-- EXAMPLE:
### config.yaml

```yaml
# Required fields
input_dir: str          # MUST be an absolute path to an existing directory
output:
  database_url: str     # MUST be a valid PostgreSQL connection string

# Optional fields
staging_db: str         # Default: "staging.db". Path to SQLite staging database
logging:
  level: str            # Default: "INFO". MUST be one of: DEBUG, INFO, WARNING, ERROR
  file: str | null      # Default: null. If set, MUST be a writable file path

# Scoring configuration
scoring:
  models: list          # Default: [{"name": "weighted_sum"}]
    - name: str         # MUST match a key in models.MODELS registry
      target_field: str # Model-specific. SHOULD match a field in the CSV headers
```
-->
