# Auto-doc Pipeline Data Flow

## Key Concepts

- **SMI (source_material_index):** Maps `DOCUMENT/section-slug` keys to source files. Created by scan, consumed by generate and verify. The bridge between documentation sections and code.
- **Orient responses:** Per-section context packets emitted by `next-heading.py` before each `##` section. Contain source files, relevant tables, column detail, and table usage. Tell the writer agent WHERE to look.
- **Typed refs:** Structured references (db, code, flow, env, config, etc.) that link prose to codebase entities. Verified by the verify step.
- **Bottom-up feeding model:** Writers receive one heading at a time via `next-heading.py`. Orient → read source → write heading → repeat. No document-level decisions.

## Data Flow

```
scan → docs-scan.json
         ├── project_model (components, tech stack, entry points)
         └── source_material_index (section → source files)

generate-setup.py:
  docs-scan.json → split-scan-by-audience.py → scan-views/
  docs-scan.json → extract-database-model.py → database-model.json
                                              → database-model-summary.json
                                              → db-usage-index.json
  db-usage-index.json + SMI → _build_db_table_map() → db-table-map.json
  db-table-map.json + database-model.json + template → next-heading.py --init → heading-state-*.json

writer agents:
  next-heading.py (runtime) → orient response → read source → write-section.py → section-*.md + refs-*.json

verify:
  docs + reference-manifests → verify agents → findings.json
```

## The Section→File→Table Bridge

The core improvement in the pipeline: how documentation sections connect to database tables.

**Old path (component-level, coarse):**
```
SMI[section].source_files → component.path prefix match → component.database_tables (class names)
```
Problem: any file under `src/db/` inherits ALL tables from that component.

**New path (file-level, precise):**
```
SMI[section].source_files → db-usage-index.file_usage[file] → {function: [table_names]}
```
The usage index is built by `extract-database-model.py --usage-output` using pure AST analysis — no imports needed. It tracks which model classes each function references.

**Result:** Orient responses now include `db_table_usage` alongside `relevant_tables`, giving writers both WHICH tables and WHERE in the code they're used.

## Audience-Specific Views

All audiences share the same underlying index. Different writer agents use the data differently:

- **devops-writer:** Uses `db_table_usage` for targeted `find_symbol` calls on listed functions. Reads `db_column_detail` for schema-accurate SQL examples.
- **developer-writer:** Uses `relevant_tables` for data model architecture context.
- **end-user-writer:** Rarely needs DB context; `relevant_tables` may be empty for most sections.
- **agent-writer:** Uses `relevant_tables` to document data contracts and constraints.
