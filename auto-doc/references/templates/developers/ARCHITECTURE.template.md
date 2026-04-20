<!-- DIATAXIS: explanation + reference -->
<!-- AUDIENCE: developers -->

# Architecture

## System Overview
<!-- PURPOSE: Provide developers with a high-level mental model of the system's
     architecture. This is the first section a new contributor reads to understand
     how the major components fit together and how data flows through the system. -->
<!-- EXAMPLE:
DataForge is a three-stage data pipeline that ingests raw CSV files, applies
configurable scoring models, and outputs ranked results to a PostgreSQL database.

```
  ┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────┐
  │  Ingest  │────>│  Transform   │────>│  Score   │────>│  Output  │
  │  (CSV)   │     │  (validate,  │     │  (model  │     │  (write  │
  │          │     │   normalize) │     │   eval)  │     │   to DB) │
  └──────────┘     └──────────────┘     └──────────┘     └──────────┘
       │                  │                   │                │
       v                  v                   v                v
   raw_files/        staging.db          scores.json      results table
```

The pipeline runs as a CLI tool (`dataforge run`) or as a scheduled Prefect flow.
Each stage is independently testable and can be run in isolation for debugging.
-->

## Design Decisions
<!-- PURPOSE: Document significant architectural choices using ADR (Architecture
     Decision Record) format. Developers need to understand not just what was
     built, but WHY specific approaches were chosen over alternatives. This
     prevents relitigating settled decisions and helps contributors make
     consistent choices. -->
<!-- EXAMPLE:
### ADR-001: SQLite for staging storage

**Status:** Accepted
**Date:** 2025-06-15

**Context:** The transform stage needs intermediate storage between ingestion
and scoring. Options considered:

| Option | Pros | Cons |
|--------|------|------|
| SQLite | Zero config, single file, fast for batch reads | No concurrent writes |
| PostgreSQL | Full SQL, concurrent access | Requires running server, extra dependency |
| In-memory dict | Fastest, no I/O | Data lost on crash, memory bound |

**Decision:** SQLite. The pipeline runs as a single process with sequential
stages, so concurrent writes are not needed. SQLite's single-file storage
simplifies deployment and testing -- each test gets a fresh temp DB.

**Consequences:**
- Transform writes are single-threaded (acceptable for batch processing)
- Tests use `tmp_path / "staging.db"` fixtures
- If concurrent pipeline runs are needed later, migrate to PostgreSQL
-->

## Data Model
<!-- PURPOSE: Define the core entities, their relationships, and key schemas.
     Developers extending the system need to understand the data structures
     that flow between components. -->
<!-- EXAMPLE:
### Core Entities

```python
@dataclass
class RawRecord:
    source_file: str
    row_index: int
    fields: dict[str, str]       # Unparsed string values from CSV
    ingested_at: datetime

@dataclass
class ScoredRecord:
    record_id: str               # SHA256(source_file + row_index)
    normalized: dict[str, Any]   # Type-converted, validated fields
    scores: dict[str, float]     # Model name -> score
    final_rank: int
```

### Relationships

```
RawRecord (1) ──ingestion──> (1) StagingRow ──scoring──> (1) ScoredRecord
                                     │
                                     └── belongs to ──> BatchRun (many-to-one)
```

### Key Schema: `staging.db`

| Table | Columns | Purpose |
|-------|---------|---------|
| `raw_records` | `id`, `source_file`, `row_index`, `fields_json`, `ingested_at` | Ingested CSV rows |
| `batch_runs` | `id`, `started_at`, `status`, `record_count` | Pipeline execution tracking |
| `scores` | `record_id`, `model_name`, `score`, `scored_at` | Model evaluation results |
-->

## Data Flow
<!-- PURPOSE: Trace the full lifecycle of a request or data item through the
     system. Developers debugging issues need to follow data from entry point
     to final output, knowing which code handles each step. -->
<!-- EXAMPLE:
### Pipeline Execution Flow

1. **CLI entry** (`cli.py:main`) -- Parses arguments, loads config from `config.yaml`
2. **Ingest** (`pipeline/ingest.py:run_ingest`) -- Reads CSV files from `raw_files/` directory
   - Validates file format (must have header row)
   - Creates `RawRecord` per row, writes to `staging.db:raw_records`
   - Returns `BatchRun` with record count
3. **Transform** (`pipeline/transform.py:run_transform`) -- Reads from `staging.db:raw_records`
   - Applies type conversions from `config.yaml:field_types`
   - Validates required fields, drops invalid records (logged to `errors.json`)
   - Updates `staging.db:raw_records.status` to `"validated"` or `"invalid"`
4. **Score** (`pipeline/score.py:run_score`) -- Reads validated records
   - Loads scoring models from `models/` directory
   - Evaluates each model against each record
   - Writes scores to `staging.db:scores`
5. **Output** (`pipeline/output.py:run_output`) -- Reads scores, computes rankings
   - Writes final results to PostgreSQL `results` table
   - Generates `report.json` summary
-->

## Component Map
<!-- PURPOSE: A scannable reference of all major components, their locations,
     responsibilities, and dependencies. This is the lookup table developers
     use when asking "where is the code that handles X?" -->
<!-- EXAMPLE:
| Component | Path | Responsibility | Dependencies |
|-----------|------|---------------|--------------|
| CLI | `cli.py` | Argument parsing, config loading | `pipeline/*` |
| Ingest | `pipeline/ingest.py` | CSV reading, raw record creation | `lib/db.py` |
| Transform | `pipeline/transform.py` | Type conversion, validation | `lib/db.py`, `lib/validators.py` |
| Score | `pipeline/score.py` | Model evaluation, scoring | `models/`, `lib/db.py` |
| Output | `pipeline/output.py` | Result ranking, DB write, reports | `lib/db.py`, `lib/reports.py` |
| DB helpers | `lib/db.py` | SQLite connection, atomic writes | stdlib `sqlite3` |
| Validators | `lib/validators.py` | Field validation rules | -- |
| Reports | `lib/reports.py` | JSON report generation | stdlib `json` |
-->

## External Integrations
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Document integrations with external APIs, services, or webhooks.
     Developers need to know what the system depends on externally, how to
     configure credentials, and what happens when external services are
     unavailable. -->
<!-- EXAMPLE:
### PostgreSQL (Output Target)

- **Purpose:** Final storage for ranked results
- **Connection:** `DATABASE_URL` environment variable
- **Timeout:** 30 seconds (configurable via `config.yaml:db_timeout`)
- **Fallback:** If unavailable, results are written to `fallback_results.json`

### OpenAI API (Optional Scoring Model)

- **Purpose:** LLM-based scoring for text fields
- **Auth:** `OPENAI_API_KEY` environment variable
- **Rate limit:** 60 requests/minute (handled by `lib/rate_limiter.py`)
- **Fallback:** Skipped if API key not set; logged as warning
-->

## Security Model
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Describe the security boundaries, authentication mechanisms,
     and authorization model. Developers modifying security-sensitive code
     need to understand the trust model and constraints. -->
<!-- EXAMPLE:
### Trust Boundaries

- **Input files:** Untrusted. All CSV fields are treated as strings until
  validated by `lib/validators.py`. No `eval()` or dynamic execution.
- **Config files:** Trusted. Loaded at startup, not modifiable at runtime.
- **Database credentials:** Via environment variables only. Never stored
  in config files or committed to git.

### Access Control

The pipeline runs as a single user process. No multi-tenant access control.
Database writes use parameterized queries (no SQL injection risk).
-->

## Error Handling & Resilience
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Error recovery patterns, retry strategies, and failure boundaries.
     Developers modifying error-handling code need to understand the established
     patterns for catching, propagating, and recovering from errors. -->
<!-- EXAMPLE:
| Error Type | Handling Pattern | Recovery |
|------------|-----------------|----------|
| ... | ... | ... |
| ... | ... | ... |
| ... | ... | ... |
-->

## Concurrency Model
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Threading model, async patterns, and locking strategies.
     Developers working on concurrent code need to understand the established
     patterns for parallelism, synchronization, and shared state management. -->
<!-- EXAMPLE:
| Pattern | Where Used | Notes |
|---------|-----------|-------|
| ... | ... | ... |
| ... | ... | ... |
| ... | ... | ... |
-->
