# Typed Refs Format

This is the canonical specification for typed code references emitted by writer agents. The `ref_validation.py` module validates against these rules.

## JSON Format

```json
{"typed_refs": [
  {"type": "db", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"},
  {"type": "code", "kind": "function", "name": "compute_finance_metrics",
   "module": "src/road_runner/flows/compute.py", "param": "recompute_stale"},
  {"type": "code", "kind": "class", "name": "EtlRun",
   "module": "src/road_runner/models.py"},
  {"type": "flow", "name": "ingest-quarterly-finance-data"},
  {"type": "env", "name": "WORKER_CONCURRENCY"},
  {"type": "config", "path": "config/field-mapping.yaml"},
  {"type": "enum", "class": "EtlRun", "field": "status", "value": "completed"},
  {"type": "dep", "name": "tenacity"},
  {"type": "literal", "name": "fmp-api"},
  {"type": "ext", "name": "pg_dump"}
]}
```

## Ref Type Table (Required Fields per Type)

| type | required fields |
|------|----------------|
| `db` | `schema`, `table`, optionally `column` |
| `code` | `kind` (function/class), `name`, optionally `module`, `param` |
| `flow` | `name` |
| `env` | `name` |
| `config` | `path` |
| `enum` | `class`, `field`, `value` |
| `dep` | `name` -- PyPI package name from pyproject.toml |
| `literal` | `name` -- named string literal found anywhere in project files (concurrency tags, worker pools, artifact keys) |
| `ext` | `name` -- external tool/command with no codebase footprint (pg_dump, VACUUM, systemctl) |

## Derivation

write-section.py derives `symbols` and `file_paths` automatically from typed_refs.
For sections with no code references, use `{"typed_refs": []}`.

If the script prints a WARNING about unresolved symbols, check which file you
read that symbol from, add the correct `module` to the code ref, and re-run.
