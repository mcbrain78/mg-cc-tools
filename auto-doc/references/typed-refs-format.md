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
| `code` | `kind` (function/class), `name`, optionally `module`, `param` |
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
