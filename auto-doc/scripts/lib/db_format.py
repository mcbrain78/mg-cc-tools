"""Shared database model formatting utilities.

Used by read-database-model.py (CLI output) and next-heading.py (inline db_column_detail).
"""


def format_table(schema_name, table_name, table_data, database_name=None):
    """Format a single table as compact text."""
    if database_name:
        lines = [f"{database_name}.{schema_name}.{table_name}:"]
    else:
        lines = [f"{schema_name}.{table_name}:"]
    for col in table_data["columns"]:
        parts = [f"  {col['name']}: {col['type']}"]
        if col.get("primary_key"):
            parts.append("PK")
        if not col.get("nullable", True) and not col.get("primary_key"):
            parts.append("NOT NULL")
        if col.get("foreign_key"):
            parts.append(f"FK({col['foreign_key']})")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def slice_and_format(model_data, table_names):
    """Filter a database model to requested tables and format as text.

    Args:
        model_data: Parsed database-model.json dict with "schemas" key.
        table_names: List of table name strings to extract.

    Returns:
        Formatted text string with one block per found table,
        separated by double newlines. Empty string if no tables found.
    """
    if not model_data or not model_data.get("schemas") or not table_names:
        return ""

    requested_set = set(table_names)
    database_name = model_data.get("database_name")
    blocks = []

    for schema_name, schema_data in model_data["schemas"].items():
        for table_name, table_data in schema_data.get("tables", {}).items():
            if table_name in requested_set:
                blocks.append(format_table(
                    schema_name, table_name, table_data, database_name,
                ))

    return "\n\n".join(blocks)
