# Typed Refs Format

This is the canonical specification for typed code references emitted by writer agents. The `ref_validation.py` module validates against these rules.

## JSON Format

```json
{"typed_refs": [
  {"type": "db", "db": "road_runner_db", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"},
  {"type": "code", "kind": "function", "name": "compute_finance_metrics",
   "module": "src/road_runner/flows/compute.py", "param": "recompute_stale"},
  {"type": "code", "kind": "class", "name": "EtlRun",
   "module": "src/road_runner/models.py"},
  {"type": "flow", "name": "ingest-quarterly-finance-data"},
  {"type": "env", "name": "WORKER_CONCURRENCY"},
  {"type": "config", "path": "config/field-mapping.yaml"},
  {"type": "enum", "class": "EtlRunStatus", "field": "status", "value": "completed"},
  {"type": "dep", "name": "tenacity"},
  {"type": "literal", "name": "fmp-api"},
  {"type": "ext", "name": "pg_dump"}
]}
```

## Ref Type Table (Required Fields per Type)

| type | required fields |
|------|----------------|
| `db` | `db` (database name), then contiguous chain: `schema`, `table`, optionally `column` |
| `code` | `kind` (function/class/variable), `name`, optionally `module`, `param`, `attr` |
| `flow` | `name` |
| `env` | `name` |
| `config` | `path` |
| `enum` | `class`, `field`, `value` |
| `dep` | `name` -- PyPI package name from pyproject.toml |
| `literal` | `name` -- named string literal found anywhere in project files (concurrency tags, worker pools, artifact keys) |
| `ext` | `name` -- external tool/command with no codebase footprint (pg_dump, VACUUM, systemctl) |

## Enum ref targets

`enum` refs validate against one of:

- **Python `enum.Enum` subclasses** -- `class` is the Enum class name; `value` matches a member name or its string value.
- **`Literal[...]` type aliases** (the modern Python pattern for constrained string sets) -- `class` is the alias name; `value` is one of the Literal values.
- **Classes with constant attrs** -- a plain class with `CONST_A = "a"` style attributes. `value` matches an attr name (case-insensitive).

**Do NOT use a SQLAlchemy model class as the enum target.** A `Mapped[str]` column with enumerated valid values does not declare those values on the model -- the authoritative set typically lives in a separate `Literal[...]` alias (often in a `types.py` module). Point the ref at the alias, not the table model.

Wrong vs. right (`field` is retained as a traceability anchor in both, identifying which typed column the value belongs to):

```json
// WRONG: DataDriftWarning is a SQLAlchemy model; the Text column's valid values are not declared on the class.
{"type": "enum", "class": "DataDriftWarning", "field": "status", "value": "new"}

// RIGHT: DriftWarningStatus = Literal["new", "investigated", "acknowledged"] (in types.py)
{"type": "enum", "class": "DriftWarningStatus", "field": "status", "value": "new"}
```

`field` is not used by `check_enum_ref` for validation, but it participates in audit clearing path resolution (`lib/ref_utils.py::path_for_ref`) and disambiguates which member of the class the value applies to. Keep it populated.

## Derivation

write-section.py derives `symbols` and `file_paths` automatically from typed_refs.
For sections with no code references, use `{"typed_refs": []}`.

If the script prints a WARNING about unresolved symbols, check which file you
read that symbol from, add the correct `module` to the code ref, and re-run.

## Completeness Rule

**Name → Ref rule:** Every code entity that appears in the section body — in backtick-quoted prose, code blocks, SQL queries, or table cells — MUST have a corresponding typed ref. This includes:
- CLI tools in code blocks → `ext` (e.g., `psql`, `curl`, `systemctl`, `pg_dump`)
- File paths in code blocks → `config` (e.g., `.env.production`, `alembic_road_runner.ini`)
- Table/column names in SQL → `db` with `column` field when columns are used
- Env vars in code blocks → `env`

**Ref → Name rule:** Every typed ref emitted MUST have its identifier appear somewhere in the section body. If you read a function during orient but described its behavior without naming it, do NOT emit a ref for it.

**Self-check before finalizing refs:** list every backticked identifier in the body and confirm each has a ref. Common misses:

- One item in a sibling set (3 base classes listed, refs for 2).
- Schema names when prose discusses them as concepts.
- Source filenames used as location markers ("defined in `X`").
- Type aliases alongside their enum values.
- Bare db names when prose names a database alone.
- Column names mentioned in prose — especially in glossary metric definitions — need db refs with the `column` field, not just table-level refs.
- Framework decorators and base classes (`@flow`, `DeclarativeBase`, `Mapped`, `Column`) — one `dep` ref per package.
- Function names mentioned without a param — emit a bare `[code:function]` ref in addition to any param-specific refs. The param-ref identifier is the param name, not the function name.

### Example

Given a code block:
```sql
psql -h $DB_HOST -d road_runner_db -c "SELECT flow_name FROM road_runner.etl_runs"
```

Required refs:
```json
{"typed_refs": [
  {"type": "ext", "name": "psql"},
  {"type": "env", "name": "DB_HOST"},
  {"type": "db", "db": "road_runner_db", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"}
]}
```

## Contextual Ref Patterns

These cases are easy to miss. Emit refs for them when the situation matches.

### Partial db refs (schema-as-concept, bare db)

The chain validator (`ref_validation.py::_db_ref_valid`) accepts any contiguous prefix of (db → schema → table → column). Use partial forms when prose discusses these as concepts, not just when SQL appears:

- "writes to the `raw_fmp` schema" → `{"type": "db", "db": "finance", "schema": "raw_fmp"}` — schema-only.
- "connects to the `finance` database" → `{"type": "db", "db": "finance"}` — bare db.
- "the `public` tables" → `{"type": "db", "db": "finance", "schema": "public"}`.

### Source file paths (`config` type, not just configs)

The `config` ref type covers **any file path in backticks**, not only configuration files. Emit a `config` ref for:

- Source files: `src/**/*.py`, `tests/conftest.py`
- Build/packaging: `pyproject.toml`, `uv.lock`
- Scripts: `bin/*.sh`
- Traditional config: `alembic.ini`, `.env.example`, `prefect.yaml`

A `code` ref's `module` field does NOT cover a prose mention of the filename itself. If prose says "defined in `src/X/Y.py`", emit a separate `config` ref for that path.

### Type aliases and constants

- Module-level constants (`MAX_RETRIES`, `TIMEOUT_MS`) → `{"type": "code", "kind": "variable", "name": "MAX_RETRIES", "module": "src/..."}`.
- `Literal[...]` type aliases named as types (e.g., `DriftSeverity`) → `{"type": "code", "kind": "class", "name": "DriftSeverity", "module": "src/types.py"}` for the alias itself. Separately, each value mentioned gets an `enum` ref.
- If prose says "a `DriftSeverity` of `critical`", emit **two refs**: one code ref for the alias, one enum ref for the value.

### Named string literals

Use `literal` for a string value that appears verbatim in code but isn't covered by class/function/file/env/dep:

- Test database names (`test_finance`)
- Worker pool / concurrency tags (`fmp-api`, `finra-api`)
- Artifact keys (`pipeline-health-summary`)
- API provider identifiers
- PostgreSQL role names (`stock_ranker`), server hostnames (`mcbrain-server2`)

### Column-level db refs for named columns

Column refs are not only for SQL queries. Any prose mention of a specific column name needs a `db` ref with the `column` field populated:

- Glossary metric definitions: "compute `peg_fwd`" → `{"type": "db", "db": "...", "schema": "...", "table": "finance_metrics", "column": "peg_fwd"}`.
- Composite keys in explanation: "the `(ticker, period_end_date)` composite key" → two column refs.
- Attribute references: "the `flow_name` column on EtlRun" → `{"type": "db", "...", "table": "etl_runs", "column": "flow_name"}`.

When a glossary section defines many metrics (e.g., ~40 `finance_metrics` column entries in one `domain-terms` block), emitting ~40 individual column refs is the expected shape — volume tracks the number of concepts defined.

### Framework decorators, types, and base classes as `dep` refs

Framework-provided decorators, type annotations, and base classes are **dependency mentions**, not project code. Emit one `dep` ref per package, not a `code` ref per usage:

- `@flow`, `@task` → `{"type": "dep", "name": "prefect"}`
- `Mapped`, `Mapped[str]`, `Mapped[Decimal | None]`, `Column`, `DeclarativeBase` → `{"type": "dep", "name": "sqlalchemy"}`
- `Completed()` (Prefect return type) → covered by the prefect dep; use `covered-by prefect` at dismissal time if the symbol stands alone.

One dep ref per framework per section — don't emit a separate dep ref for each decorator or type instance.

### Bare function refs alongside param-specific refs

When prose mentions a function BY NAME (not just by one of its parameters), emit a bare `<function name="X" module="..."/>` ref in addition to any `<function><param>` variants. The clearing identifier for a param ref is the **param name**, not the function name — so prose mentioning the function without a param can't match a declared param-scoped ref.

Prose: "the `compute_finance_metrics` flow accepts `tickers` and `recompute_stale`"

Required refs (three elements):
- `<function name="compute_finance_metrics" module="src/.../compute.py"/>` — bare, clears prose mentions of the function name alone.
- `<function name="compute_finance_metrics" module="src/.../compute.py"><param>tickers</param></function>` — for the `tickers` mention.
- `<function name="compute_finance_metrics" module="src/.../compute.py"><param>recompute_stale</param></function>` — for the `recompute_stale` mention.
