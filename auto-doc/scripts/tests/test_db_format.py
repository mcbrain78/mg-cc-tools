"""Tests for lib/db_format.py -- shared database formatting utilities."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.db_format import format_table, slice_and_format


def _make_db_model():
    return {
        "schemas": {
            "road_runner": {
                "tables": {
                    "etl_runs": {
                        "columns": [
                            {"name": "id", "type": "Integer", "primary_key": True, "nullable": False, "foreign_key": None},
                            {"name": "flow_name", "type": "String(100)", "primary_key": False, "nullable": False, "foreign_key": None},
                            {"name": "ticker_id", "type": "Integer", "primary_key": False, "nullable": False, "foreign_key": "road_runner.stocks.id"},
                        ]
                    },
                    "stocks": {
                        "columns": [
                            {"name": "id", "type": "Integer", "primary_key": True, "nullable": False, "foreign_key": None},
                            {"name": "ticker", "type": "String(10)", "primary_key": False, "nullable": False, "foreign_key": None},
                        ]
                    },
                }
            },
            "raw_fmp": {
                "tables": {
                    "raw_income": {
                        "columns": [
                            {"name": "id", "type": "Integer", "primary_key": True, "nullable": False, "foreign_key": None},
                            {"name": "revenue", "type": "Numeric", "primary_key": False, "nullable": True, "foreign_key": None},
                        ]
                    }
                }
            }
        }
    }


class TestFormatTable:
    """format_table produces compact text for a single table."""

    def test_schema_qualified_header(self):
        model = _make_db_model()
        table_data = model["schemas"]["road_runner"]["tables"]["stocks"]
        result = format_table("road_runner", "stocks", table_data)
        assert result.startswith("road_runner.stocks:")

    def test_pk_annotation(self):
        model = _make_db_model()
        table_data = model["schemas"]["road_runner"]["tables"]["stocks"]
        result = format_table("road_runner", "stocks", table_data)
        assert "PK" in result

    def test_fk_annotation(self):
        model = _make_db_model()
        table_data = model["schemas"]["road_runner"]["tables"]["etl_runs"]
        result = format_table("road_runner", "etl_runs", table_data)
        assert "FK(road_runner.stocks.id)" in result

    def test_not_null_annotation(self):
        model = _make_db_model()
        table_data = model["schemas"]["road_runner"]["tables"]["etl_runs"]
        result = format_table("road_runner", "etl_runs", table_data)
        assert "NOT NULL" in result

    def test_nullable_column_no_not_null(self):
        model = _make_db_model()
        table_data = model["schemas"]["raw_fmp"]["tables"]["raw_income"]
        result = format_table("raw_fmp", "raw_income", table_data)
        lines = result.split("\n")
        revenue_line = [line for line in lines if "revenue" in line][0]
        assert "NOT NULL" not in revenue_line


class TestSliceAndFormat:
    """slice_and_format filters model to requested tables."""

    def test_single_table(self):
        result = slice_and_format(_make_db_model(), ["stocks"])
        assert "road_runner.stocks:" in result
        assert "etl_runs" not in result

    def test_multiple_tables(self):
        result = slice_and_format(_make_db_model(), ["etl_runs", "stocks"])
        assert "road_runner.etl_runs:" in result
        assert "road_runner.stocks:" in result

    def test_tables_across_schemas(self):
        result = slice_and_format(_make_db_model(), ["stocks", "raw_income"])
        assert "road_runner.stocks:" in result
        assert "raw_fmp.raw_income:" in result

    def test_missing_table_ignored(self):
        result = slice_and_format(_make_db_model(), ["nonexistent"])
        assert result == ""

    def test_empty_table_list(self):
        result = slice_and_format(_make_db_model(), [])
        assert result == ""

    def test_none_model(self):
        result = slice_and_format(None, ["stocks"])
        assert result == ""

    def test_no_schemas_key(self):
        result = slice_and_format({"other": "data"}, ["stocks"])
        assert result == ""

    def test_blocks_separated_by_double_newline(self):
        result = slice_and_format(_make_db_model(), ["etl_runs", "stocks"])
        assert "\n\n" in result
