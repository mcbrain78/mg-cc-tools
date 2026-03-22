<!-- DIATAXIS: reference -->
<!-- AUDIENCE: agents -->

# Gotchas

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Edge Cases
<!-- PURPOSE: Specific behaviors that are non-obvious or counter-intuitive.
     Agents MUST be aware of these when generating or modifying code that
     touches the described areas. Each edge case MUST include the trigger
     condition, the non-obvious behavior, and the correct handling. -->
<!-- EXAMPLE:
### Empty CSV Files

- **Trigger:** An input CSV file exists but contains only a header row (no data rows)
- **Behavior:** `run_ingest()` returns `BatchRun(record_count=0)` without error. The
  batch is recorded in `staging.db:batch_runs` with status `"empty"`.
- **Correct handling:** Check `batch_run.record_count > 0` before proceeding to
  transform stage. An empty batch MUST NOT cause a pipeline failure.
- **What breaks if ignored:** Transform stage processes zero records and returns
  `TransformResult(valid_count=0)`, which causes the score stage to skip silently.
  The output stage then writes zero results to PostgreSQL, which may overwrite
  previous valid results if `config.output.truncate_first` is `true`.

### Unicode in CSV Fields

- **Trigger:** CSV files contain non-ASCII characters (accented names, CJK text,
  emoji in text fields)
- **Behavior:** The ingest stage opens files with `encoding="utf-8"`. If a file
  uses a different encoding (Latin-1, Shift-JIS), `UnicodeDecodeError` is raised.
- **Correct handling:** The CSV file encoding MUST be UTF-8. If encoding issues
  are expected, add `encoding` to `config.yaml:ingest` and pass to `open()`.
- **What breaks if ignored:** Pipeline crashes mid-batch. Records already written
  to `staging.db` remain, causing duplicate records on retry.

### Score of Exactly 0.0

- **Trigger:** A scoring model returns `0.0` for a record
- **Behavior:** The record is included in output with `final_rank` assigned.
  A score of `0.0` is valid -- it means "lowest possible score", not "unscored."
- **Correct handling:** MUST NOT filter out records with `score == 0.0`. Use
  `score is None` to detect unscored records.
- **What breaks if ignored:** Records with legitimate zero scores are excluded
  from output, creating silent data loss.
-->

## Ordering Constraints
<!-- PURPOSE: Operations that MUST happen in a specific sequence. Agents MUST
     respect these ordering requirements when modifying code flow. Each
     constraint MUST specify what breaks if the order is violated. -->
<!-- EXAMPLE:
### Pipeline Stage Order

Stages MUST execute in this exact order:

1. **Ingest** (writes `raw_records` to staging DB)
2. **Transform** (reads `raw_records`, updates `status` column)
3. **Score** (reads validated records, writes `scores`)
4. **Output** (reads scores, writes to PostgreSQL)

**What breaks if violated:**
- Score before Transform: Attempts to score un-validated records. Type errors
  on fields that haven't been converted (e.g., string "42.5" instead of float).
- Output before Score: `staging.db:scores` table is empty. Output stage writes
  zero results to PostgreSQL.

### Database Schema Creation

`lib/db.py:create_tables()` MUST be called before any read/write operations.
`get_connection()` calls `create_tables()` automatically when the database
file does not exist. If the file exists but has a stale schema, the pipeline
MUST be re-initialized:

```bash
rm staging.db
dataforge run --stage ingest
```

**What breaks if violated:** `sqlite3.OperationalError: no such table: raw_records`

### Model Registration Before Config Loading

All model classes MUST be registered in `models.MODELS` before `config.yaml`
is loaded and validated. The config validator checks that each
`scoring.models[].name` exists in the `MODELS` dict.

**What breaks if violated:** `ValueError: Unknown model 'percentile'. Available: weighted_sum, llm`
-->

## Invariants
<!-- PURPOSE: Conditions that MUST always be true during system operation.
     Agents MUST NOT generate code that violates these invariants. Each
     invariant MUST include how to verify it holds. -->
<!-- EXAMPLE:
### Score Range

All scoring model `score()` methods MUST return a float in the range `[0.0, 1.0]`.

- **Verification:** `assert 0.0 <= score <= 1.0` in `BaseModel.score()` wrapper
- **Enforced by:** `BaseModel.__init_subclass__()` wraps `score()` with range check
- **What breaks:** Output ranking assumes scores are normalized. Out-of-range scores
  produce incorrect `final_rank` values.

### Atomic Writes

All file writes (JSON, CSV reports) MUST use the atomic write pattern
(`tempfile` + `os.replace()`). Direct `open(path, "w")` is prohibited.

- **Verification:** Grep for `open(.*"w")` -- should only appear inside
  `tempfile.NamedTemporaryFile` context
- **What breaks:** Crash during write leaves a corrupted or empty file. The next
  pipeline run reads the corrupted file and fails with `json.JSONDecodeError`.

### Batch ID Uniqueness

Every `BatchRun.batch_id` MUST be unique across all pipeline runs. Generated
as `f"{timestamp}_{random_hex(8)}"` in `pipeline/ingest.py`.

- **Verification:** `SELECT batch_id, COUNT(*) FROM batch_runs GROUP BY batch_id HAVING COUNT(*) > 1` returns zero rows
- **What breaks:** Duplicate batch IDs cause transform/score stages to process
  records from multiple runs, producing incorrect results.
-->

## Common Mistakes
<!-- PURPOSE: Mistakes that are frequently made when modifying this codebase.
     Agents MUST check for these patterns in generated code. Table format
     for quick scanning. -->
<!-- EXAMPLE:
| Mistake | Symptom | Fix |
|---------|---------|-----|
| Using `config["key"]` instead of `config.get("key", default)` | `KeyError` when optional config key is missing | Use `.get()` with a sensible default for all optional keys |
| Forgetting to register a new model in `models.MODELS` | `ValueError: Unknown model` at config validation | Add entry to `MODELS` dict in `models/__init__.py` |
| Using `f-string` in SQL query | SQL injection vulnerability (and `sqlite3.ProgrammingError` on some inputs) | Use parameterized queries: `cursor.execute("... WHERE id=?", (id,))` |
| Importing from `__init__.py` internals | `ImportError` when module reorganized | Import from the defining module directly |
| Writing to `staging.db` without a transaction | Partial writes on crash; duplicate records on retry | Use `atomic_write()` or explicit `conn.commit()` in a `try/finally` |
| Assuming CSV field order | Breaks when CSV columns are reordered | Access fields by header name, not index: `row["name"]` not `row[0]` |
| Logging with `print()` | Output not captured by logging infrastructure, not filterable | Use `logger.info()` with structured data |
-->

## Platform-Specific Gotchas
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Behaviors that differ across operating systems or runtime
     environments. Agents MUST be aware of these when generating code
     that may run in different environments. -->
<!-- EXAMPLE:
### File Path Separators

- `os.path.join()` MUST be used for all path construction
- MUST NOT use hardcoded `/` or `\\` separators
- `pathlib.Path` is acceptable but not used in this codebase (convention: use `os.path`)

### SQLite File Locking on NFS

SQLite does not support concurrent access over NFS. The staging database
MUST be on a local filesystem. If running in a container, mount a local
volume for `staging.db`.

**Symptom:** `sqlite3.OperationalError: database is locked` despite no other processes
**Fix:** Move `staging.db` path to a local filesystem
-->

## Performance Gotchas
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Non-obvious performance characteristics. Agents SHOULD be aware
     of these when generating code that processes large datasets or runs in
     performance-sensitive contexts. -->
<!-- EXAMPLE:
### Batch Size for Ingest

Inserting records one-at-a-time into SQLite is ~100x slower than batch inserts.
`atomic_write()` handles batching automatically. MUST NOT call `atomic_write()`
in a loop -- pass all rows at once.

```python
# Correct: single batch write
atomic_write(conn, "raw_records", all_rows)

# Incorrect: per-row writes (~100x slower)
for row in all_rows:
    atomic_write(conn, "raw_records", [row])
```

### OpenAI API Rate Limiting

The LLM scorer processes records sequentially with rate limiting (60 req/min).
For datasets with more than 1000 records, scoring takes 15+ minutes. Consider
using the `weighted_sum` model for development and reserving `llm` for production.
-->
